"""`photos.directory` is derived by the database, and stays that way.

The folder count and folder tree read this column instead of computing
regexp_replace(path, ...) per row, which is what made both queries sequential
scans. Storing a copy of part of `path` is only safe because Postgres owns it:
these tests pin that it is written on insert, recomputed on a path change, and
cannot be set by hand — the failure mode being an organize move that leaves a
photo filed under the folder it came from.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app.models import Photo, ScanRoot
from app.services.folders import build_folder_tree
from app.services.stats import compute_stats
from tests.images import make_image


@pytest.fixture
def photo_at(db_session: Session) -> object:
    root = ScanRoot(path="/lib", enabled=True)
    db_session.add(root)
    db_session.commit()
    counter = {"n": 0}

    def _add(path: str, status: str = "active") -> Photo:
        counter["n"] += 1
        photo = Photo(
            root_id=root.id,
            path=path,
            filename=Path(path).name,
            ext="jpg",
            mime="image/jpeg",
            size_bytes=100,
            mtime_ns=counter["n"],
            status=status,
        )
        db_session.add(photo)
        db_session.commit()
        return photo

    return _add


def test_the_directory_is_filled_in_from_the_path(db_session: Session, photo_at) -> None:  # type: ignore[no-untyped-def]
    photo = photo_at("/lib/2019/summer/beach.jpg")

    assert photo.directory == "/lib/2019/summer"


def test_moving_a_photo_refiles_it_without_anyone_updating_the_directory(
    db_session: Session,
    photo_at,  # type: ignore[no-untyped-def]
) -> None:
    """The organize workflow rewrites `path` and nothing else. If `directory`
    were an ordinary column, every moved photo would stay in its old folder."""
    photo = photo_at("/lib/inbox/beach.jpg")
    assert photo.directory == "/lib/inbox"

    photo.path = "/lib/2019/summer/beach.jpg"
    db_session.commit()
    db_session.refresh(photo)

    assert photo.directory == "/lib/2019/summer"


def test_the_directory_cannot_be_written_by_hand(db_session: Session, photo_at) -> None:  # type: ignore[no-untyped-def]
    """Postgres rejects the write, so no code path can put the two out of step."""
    photo = photo_at("/lib/inbox/beach.jpg")

    with pytest.raises(DatabaseError):
        db_session.execute(
            Photo.__table__.update().where(Photo.id == photo.id).values(directory="/somewhere/else")
        )
    db_session.rollback()


def test_a_photo_in_the_root_itself_gets_the_root_as_its_directory(
    db_session: Session,
    photo_at,  # type: ignore[no-untyped-def]
) -> None:
    """regexp_replace strips the last segment; a file directly under the root
    must not end up with an empty directory."""
    photo = photo_at("/lib/beach.jpg")

    assert photo.directory == "/lib"


def test_the_folder_count_matches_the_folders_actually_present(
    db_session: Session,
    photo_at,  # type: ignore[no-untyped-def]
) -> None:
    """stats and the folder tree read the same column two different ways; they
    must not disagree about how many folders there are."""
    for path in (
        "/lib/2019/a.jpg",
        "/lib/2019/b.jpg",
        "/lib/2020/c.jpg",
        "/lib/2020/sub/d.jpg",
        "/lib/e.jpg",
    ):
        photo_at(path)

    counted = compute_stats(db_session).folders
    distinct_dirs = {
        row.directory
        for row in db_session.scalars(select(Photo).where(Photo.status == "active")).all()
    }

    assert counted == len(distinct_dirs) == 4


def test_a_quarantined_photo_leaves_the_folder_count(
    db_session: Session,
    photo_at,  # type: ignore[no-untyped-def]
) -> None:
    photo_at("/lib/2019/a.jpg")
    photo_at("/lib/gone/b.jpg", status="quarantined")

    assert compute_stats(db_session).folders == 1


def test_the_folder_tree_still_rolls_counts_up_to_the_root(
    client: TestClient, tmp_path: Path
) -> None:
    """End to end past the query change: the tree's shape and its recursive
    counts are what the Library sidebar renders."""
    make_image(tmp_path / "top.jpg")
    make_image(tmp_path / "2019" / "a.jpg")
    make_image(tmp_path / "2019" / "trip" / "b.jpg")
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202

    tree = {node["path"]: node for node in client.get("/api/folders").json()}

    root = tree[str(tmp_path)]
    assert root["photo_count"] == 3  # includes descendants
    assert root["direct_count"] == 1
    assert tree[str(tmp_path / "2019")]["photo_count"] == 2
    assert tree[str(tmp_path / "2019" / "trip")]["direct_count"] == 1


def test_the_tree_and_the_count_agree_after_a_scan(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "a.jpg")
    make_image(tmp_path / "one" / "b.jpg")
    make_image(tmp_path / "two" / "c.jpg")
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202

    stats_folders = client.get("/api/stats").json()["folders"]
    tree_nodes = client.get("/api/folders").json()

    assert stats_folders == 3
    assert {node["path"] for node in tree_nodes} == {
        str(tmp_path),
        str(tmp_path / "one"),
        str(tmp_path / "two"),
    }


def test_build_folder_tree_reads_the_stored_column(db_session: Session, photo_at) -> None:  # type: ignore[no-untyped-def]
    """A regression guard on the query itself: if it went back to deriving the
    directory per row this would still pass, so it asserts the shape instead —
    the tree must be built from directories, not filenames."""
    photo_at("/lib/2019/a.jpg")
    photo_at("/lib/2019/b.jpg")

    nodes = {node.path: node for node in build_folder_tree(db_session)}

    assert "/lib/2019" in nodes
    assert nodes["/lib/2019"].direct_count == 2
    assert not any(node.path.endswith(".jpg") for node in nodes.values())
