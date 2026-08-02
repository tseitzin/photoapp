import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Photo, Scan
from app.services import duplicates
from app.services.scans import recover_interrupted_scans
from tests.images import make_image, make_textured_image


def _add_root(client: TestClient, path: Path) -> int:
    response = client.post("/api/scan-roots", json={"path": str(path)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _run_scan(client: TestClient) -> dict:
    response = client.post("/api/scans", json={})
    assert response.status_code == 202, response.text
    return client.get(f"/api/scans/{response.json()['id']}").json()


def test_deleted_file_is_marked_missing_not_purged(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    doomed = make_image(tmp_path / "doomed.jpg", color="red")
    make_image(tmp_path / "keeper.jpg", color="green")
    _add_root(client, tmp_path)
    _run_scan(client)

    doomed.unlink()
    scan = _run_scan(client)

    assert scan["status"] == "completed"
    assert scan["files_missing"] == 1
    photos = {p.filename: p for p in db_session.scalars(select(Photo)).all()}
    assert len(photos) == 2, "missing photo row must be retained"
    assert photos["doomed.jpg"].status == "missing"
    assert photos["keeper.jpg"].status == "active"


def test_reappearing_file_becomes_active_again(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    photo_path = make_image(tmp_path / "back.jpg", color="purple")
    backup = photo_path.read_bytes()
    _add_root(client, tmp_path)
    _run_scan(client)
    photo_path.unlink()
    _run_scan(client)

    photo_path.write_bytes(backup)
    scan = _run_scan(client)

    assert scan["status"] == "completed"
    photo = db_session.scalars(select(Photo)).one()
    db_session.refresh(photo)
    assert photo.status == "active"


def test_moved_file_keeps_its_photo_id_and_updates_path(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    src = make_image(tmp_path / "2023/original.jpg", color="teal")
    _add_root(client, tmp_path)
    _run_scan(client)
    original = db_session.scalars(select(Photo)).one()
    original_id = original.id

    dest = tmp_path / "2024/renamed.jpg"
    dest.parent.mkdir(parents=True)
    shutil.move(src, dest)
    scan = _run_scan(client)

    assert scan["status"] == "completed"
    assert scan["files_moved"] == 1
    assert scan["files_added"] == 0
    assert scan["files_missing"] == 0
    photo = db_session.scalars(select(Photo)).one()
    db_session.refresh(photo)
    assert photo.id == original_id
    assert photo.path == str(dest)
    assert photo.filename == "renamed.jpg"
    assert photo.status == "active"


def test_move_across_roots_is_detected(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    root_b.mkdir()
    src = make_image(root_a / "wanderer.jpg", color="orange")
    _add_root(client, root_a)
    id_b = _add_root(client, root_b)
    _run_scan(client)
    original_id = db_session.scalars(select(Photo)).one().id

    shutil.move(src, root_b / "wanderer.jpg")
    scan = _run_scan(client)

    assert scan["files_moved"] == 1
    photo = db_session.scalars(select(Photo)).one()
    db_session.refresh(photo)
    assert photo.id == original_id
    assert photo.root_id == id_b


def test_a_rescan_that_finds_no_changes_skips_the_duplicate_rebuild(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rebuild is the most expensive part of a scan and is a pure function
    of the active photo rows — if nothing changed, it has nothing to do."""
    make_image(tmp_path / "a.jpg", color="red")
    _add_root(client, tmp_path)
    _run_scan(client)

    calls = 0
    real = duplicates.rebuild_duplicate_groups

    def counting(session: Session) -> object:
        nonlocal calls
        calls += 1
        return real(session)

    monkeypatch.setattr(duplicates, "rebuild_duplicate_groups", counting)

    unchanged = _run_scan(client)
    assert unchanged["status"] == "completed"
    assert unchanged["files_unchanged"] == 1
    assert calls == 0, "nothing changed, yet the groups were rebuilt"

    make_image(tmp_path / "b.jpg", color="green")
    changed = _run_scan(client)
    assert changed["files_added"] == 1
    assert calls == 1, "a scan that added a photo must refresh the groups"


def test_skipping_the_rebuild_leaves_existing_duplicate_groups_intact(
    client: TestClient, tmp_path: Path
) -> None:
    """A no-op rescan must not disturb groups the user has already reviewed."""
    original = make_textured_image(tmp_path / "original.jpg", seed=3)
    (tmp_path / "copy.jpg").write_bytes(original.read_bytes())
    _add_root(client, tmp_path)
    _run_scan(client)
    before = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()
    assert before["total"] == 1

    _run_scan(client)

    after = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()
    assert after["total"] == 1
    assert after["items"][0]["id"] == before["items"][0]["id"]
    assert len(after["items"][0]["members"]) == 2


def test_interrupted_scans_are_failed_by_startup_recovery(db_session: Session) -> None:
    db_session.add(Scan(status="running"))
    db_session.add(Scan(status="pending"))
    db_session.add(Scan(status="completed"))
    db_session.commit()

    recovered = recover_interrupted_scans(db_session)

    assert recovered == 2
    statuses = sorted(s.status for s in db_session.scalars(select(Scan)).all())
    assert statuses == ["completed", "failed", "failed"]
    failed = db_session.scalar(select(Scan).where(Scan.status == "failed"))
    assert failed is not None
    assert "Interrupted" in (failed.message or "")
