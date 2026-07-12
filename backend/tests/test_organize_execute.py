"""Organize executor: files move, the index follows, everything is audited."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.files.organize import OrganizeSpec, execute_organize
from app.models import FileOperation, OrganizeRun, Photo
from app.repositories.organize import OrganizeRunRepository
from tests.images import make_image, make_textured_image

CAPTURED = {36867: "2024:07:15 14:30:22"}


def _index(client: TestClient, *roots: Path) -> None:
    for root in roots:
        assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _run(
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    root: Path,
    folders: list[Path],
    **overrides: object,
) -> OrganizeRun:
    params: dict[str, object] = {
        "folders": [str(f) for f in folders],
        "destination": str(root / "Organized"),
        "mode": "date",
        "rename": False,
        "skip_duplicates": True,
    }
    params.update(overrides)
    OrganizeSpec.from_params(params)  # fail fast on malformed test setup
    run = OrganizeRunRepository(db_session).create(params, str(uuid4()))
    execute_organize(run.id, db_session_factory)
    db_session.expire_all()  # the job used its own session; drop stale state
    return db_session.get(OrganizeRun, run.id)  # type: ignore[return-value]


def test_executing_a_run_moves_files_updates_paths_and_audits_with_one_batch_id(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg", exif_ifd_fields=CAPTURED)
    make_image(tmp_path / "inbox" / "b.png", color="tomato")  # undated
    _index(client, tmp_path)

    run = _run(db_session, db_session_factory, tmp_path, [tmp_path / "inbox"])

    assert run.status == "completed"
    assert run.moved == 2 and run.failed_count == 0
    dated = tmp_path / "Organized" / "2024" / "07" / "a.jpg"
    undated = tmp_path / "Organized" / "Undated" / "b.png"
    assert dated.is_file() and undated.is_file()
    assert not (tmp_path / "inbox" / "a.jpg").exists()
    paths = set(db_session.scalars(select(Photo.path)))
    assert {str(dated), str(undated)} <= paths
    ops = db_session.scalars(select(FileOperation).where(FileOperation.op == "organize")).all()
    assert len(ops) == 2
    assert {op.batch_id for op in ops} == {run.batch_id}
    assert all(op.dest_path and op.size_bytes for op in ops)


def test_cross_root_move_updates_root_id(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "drive_a"
    dest_root = tmp_path / "drive_b"
    make_image(source_root / "inbox" / "a.jpg", exif_ifd_fields=CAPTURED)
    dest_root.mkdir()
    _index(client, source_root, dest_root)
    roots = {r["path"]: r["id"] for r in client.get("/api/scan-roots").json()}

    run = _run(
        db_session,
        db_session_factory,
        source_root,
        [source_root / "inbox"],
        destination=str(dest_root / "Organized"),
    )

    assert run.status == "completed" and run.moved == 1
    photo = db_session.scalar(select(Photo))
    assert photo is not None
    assert photo.path == str(dest_root / "Organized" / "2024" / "07" / "a.jpg")
    assert photo.root_id == roots[str(dest_root)]


def test_missing_source_file_is_counted_failed_and_the_run_continues(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    make_image(tmp_path / "inbox" / "gone.jpg", exif_ifd_fields=CAPTURED)
    make_image(tmp_path / "inbox" / "stays.jpg", color="tomato", exif_ifd_fields=CAPTURED)
    _index(client, tmp_path)
    (tmp_path / "inbox" / "gone.jpg").unlink()  # disk changed after planning

    run = _run(db_session, db_session_factory, tmp_path, [tmp_path / "inbox"])

    assert run.status == "completed"
    assert run.moved == 1
    assert run.failed_count == 1
    assert run.message and "gone.jpg" in run.message
    assert (tmp_path / "Organized" / "2024" / "07" / "stays.jpg").is_file()


def test_collision_with_existing_file_on_disk_gets_a_suffix(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    make_image(tmp_path / "inbox" / "x.png")
    _index(client, tmp_path)
    # An unindexed file appears at the planned destination before execution.
    make_image(tmp_path / "Organized" / "Undated" / "x.png", color="tomato")

    run = _run(db_session, db_session_factory, tmp_path, [tmp_path / "inbox"])

    assert run.status == "completed" and run.moved == 1
    assert (tmp_path / "Organized" / "Undated" / "x_01.png").is_file()
    assert (tmp_path / "Organized" / "Undated" / "x.png").is_file()  # untouched


def test_duplicate_groups_are_unchanged_after_organizing(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    original = make_textured_image(tmp_path / "inbox" / "dup.jpg", seed=1)
    (tmp_path / "inbox" / "dup_copy.jpg").write_bytes(original.read_bytes())
    _index(client, tmp_path)
    before = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()["items"][0]

    run = _run(
        db_session, db_session_factory, tmp_path, [tmp_path / "inbox"], skip_duplicates=False
    )

    assert run.status == "completed" and run.moved == 2
    after = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()["items"][0]
    assert after["id"] == before["id"]
    assert len(after["members"]) == 2
    assert after["keeper_photo_id"] == before["keeper_photo_id"]


def test_run_failure_marks_the_run_failed_with_a_message(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg")
    _index(client, tmp_path)

    run = _run(db_session, db_session_factory, tmp_path, [tmp_path / "inbox"], mode="bogus")

    assert run.status == "failed"
    assert run.message and "bogus" in run.message
    assert (tmp_path / "inbox" / "a.jpg").is_file()  # nothing moved
