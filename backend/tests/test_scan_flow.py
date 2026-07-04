import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Photo, Scan
from app.services.scans import execute_scan
from tests.images import make_image


def _add_root(client: TestClient, path: Path) -> int:
    response = client.post("/api/scan-roots", json={"path": str(path)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _run_scan(client: TestClient, root_ids: list[int] | None = None) -> dict:
    response = client.post("/api/scans", json={"root_ids": root_ids})
    assert response.status_code == 202, response.text
    scan = client.get(f"/api/scans/{response.json()['id']}").json()
    return scan


def test_scan_indexes_new_photos_with_hash_and_dimensions(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "a.jpg", size=(100, 60))
    make_image(tmp_path / "2024/b.png", size=(40, 40))
    make_image(tmp_path / "2024/trip/c.webp")
    _add_root(client, tmp_path)

    scan = _run_scan(client)

    assert scan["status"] == "completed"
    assert scan["files_found"] == 3
    assert scan["files_added"] == 3
    assert scan["files_processed"] == 3
    assert scan["error_count"] == 0
    assert scan["started_at"] and scan["finished_at"]

    photos = db_session.scalars(select(Photo)).all()
    assert len(photos) == 3
    by_name = {p.filename: p for p in photos}
    assert by_name["a.jpg"].width == 100
    assert by_name["a.jpg"].sha256 is not None
    assert len(by_name["a.jpg"].sha256) == 64
    assert by_name["b.png"].mime == "image/png"
    assert all(p.status == "active" for p in photos)


def test_scan_extracts_exif_capture_date_and_camera(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(
        tmp_path / "shot.jpg",
        exif_fields={271: "Apple", 272: "iPhone 15 Pro"},
        exif_ifd_fields={36867: "2024:05:01 09:30:00"},
    )
    _add_root(client, tmp_path)

    scan = _run_scan(client)

    assert scan["status"] == "completed"
    photo = db_session.scalars(select(Photo)).one()
    assert photo.camera_model == "iPhone 15 Pro"
    assert photo.captured_at is not None
    assert photo.captured_at.year == 2024


def test_rescan_skips_unchanged_files(client: TestClient, tmp_path: Path) -> None:
    for name in ("a.jpg", "b.jpg"):
        make_image(tmp_path / name)
    _add_root(client, tmp_path)
    first = _run_scan(client)
    assert first["files_added"] == 2

    second = _run_scan(client)

    assert second["status"] == "completed"
    assert second["files_found"] == 2
    assert second["files_unchanged"] == 2
    assert second["files_added"] == 0
    assert second["files_changed"] == 0


def test_modified_file_is_reprocessed_and_hash_updated(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    photo_path = make_image(tmp_path / "a.jpg", color="red")
    _add_root(client, tmp_path)
    _run_scan(client)
    old_sha = db_session.scalars(select(Photo)).one().sha256

    make_image(photo_path, color="blue", size=(99, 44))
    os.utime(photo_path, ns=(photo_path.stat().st_atime_ns, photo_path.stat().st_mtime_ns + 10**9))

    second = _run_scan(client)

    assert second["files_changed"] == 1
    photo = db_session.scalars(select(Photo)).one()
    db_session.refresh(photo)
    assert photo.sha256 != old_sha
    assert photo.width == 99


def test_corrupt_image_is_indexed_with_error_and_scan_completes(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    (tmp_path / "broken.jpg").write_bytes(b"this is not a jpeg")
    make_image(tmp_path / "fine.jpg")
    _add_root(client, tmp_path)

    scan = _run_scan(client)

    assert scan["status"] == "completed"
    assert scan["files_added"] == 2
    assert scan["error_count"] == 1
    broken = db_session.scalar(select(Photo).where(Photo.filename == "broken.jpg"))
    assert broken is not None
    assert broken.sha256 is not None
    assert broken.last_error is not None
    assert broken.width is None

    errors = client.get(f"/api/scans/{scan['id']}/errors").json()
    assert errors["total"] == 1
    assert errors["items"][0]["path"].endswith("broken.jpg")


def test_scan_scoped_to_selected_roots(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    make_image(root_a / "a.jpg")
    make_image(root_b / "b.jpg")
    id_a = _add_root(client, root_a)
    _add_root(client, root_b)

    scan = _run_scan(client, root_ids=[id_a])

    assert scan["files_found"] == 1
    photo = db_session.scalars(select(Photo)).one()
    assert photo.filename == "a.jpg"


def test_disabled_roots_are_not_scanned_by_default(client: TestClient, tmp_path: Path) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    make_image(root_a / "a.jpg")
    make_image(root_b / "b.jpg")
    _add_root(client, root_a)
    id_b = _add_root(client, root_b)
    client.patch(f"/api/scan-roots/{id_b}", json={"enabled": False})

    scan = _run_scan(client)

    assert scan["files_found"] == 1


def test_starting_a_scan_while_one_is_active_is_rejected(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "a.jpg")
    _add_root(client, tmp_path)
    db_session.add(Scan(status="running"))
    db_session.commit()

    response = client.post("/api/scans", json={})

    assert response.status_code == 409


def test_scan_without_any_enabled_roots_is_rejected(client: TestClient) -> None:
    response = client.post("/api/scans", json={})

    assert response.status_code == 422


def test_scan_with_unknown_root_ids_is_rejected(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/scans", json={"root_ids": [12345]})

    assert response.status_code == 422


def test_cancelled_scan_is_finalized_without_processing(
    client: TestClient,
    db_session: Session,
    db_session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    make_image(tmp_path / "a.jpg")
    _add_root(client, tmp_path)
    db_session.add(Scan(status="pending"))
    db_session.commit()
    scan_id = db_session.scalars(select(Scan)).one().id

    cancel = client.post(f"/api/scans/{scan_id}/cancel")
    assert cancel.status_code == 200

    execute_scan(scan_id, db_session_factory)

    result = client.get(f"/api/scans/{scan_id}").json()
    assert result["status"] == "cancelled"
    assert result["finished_at"] is not None
    assert result["files_found"] == 0


def test_cancelling_a_finished_scan_is_rejected(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "a.jpg")
    _add_root(client, tmp_path)
    scan = _run_scan(client)

    response = client.post(f"/api/scans/{scan['id']}/cancel")

    assert response.status_code == 409


def test_unreadable_file_is_recorded_as_error_and_scan_continues(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    locked = make_image(tmp_path / "locked.jpg")
    make_image(tmp_path / "open.jpg")
    _add_root(client, tmp_path)
    locked.chmod(0o000)
    try:
        scan = _run_scan(client)
    finally:
        locked.chmod(0o644)

    assert scan["status"] == "completed"
    assert scan["error_count"] == 1
    assert scan["files_added"] == 1
    photos = db_session.scalars(select(Photo)).all()
    assert [p.filename for p in photos] == ["open.jpg"]
