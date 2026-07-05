from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Photo
from tests.images import make_image, make_textured_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def test_stats_reflect_indexed_library(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "a.jpg", color="coral")
    make_image(tmp_path / "2024/b.jpg", color="navy")
    _index(client, tmp_path)

    stats = client.get("/api/stats").json()

    assert stats["photos"] == 2
    assert stats["storage_bytes"] > 0
    assert stats["folders"] == 2
    assert stats["duplicate_photos"] == 0
    assert stats["last_scan_at"] is not None


def test_stats_count_exact_duplicates_and_reclaimable_bytes(
    client: TestClient, tmp_path: Path
) -> None:
    original = make_image(tmp_path / "orig.jpg", color="crimson")
    (tmp_path / "copy1.jpg").write_bytes(original.read_bytes())
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/copy2.jpg").write_bytes(original.read_bytes())
    make_image(tmp_path / "unique.jpg", color="lime")
    _index(client, tmp_path)

    stats = client.get("/api/stats").json()

    assert stats["photos"] == 4
    # 3 identical copies -> 2 redundant
    assert stats["duplicate_photos"] == 2
    assert stats["reclaimable_bytes"] == 2 * original.stat().st_size


def test_stats_on_empty_library(client: TestClient) -> None:
    stats = client.get("/api/stats").json()

    assert stats["photos"] == 0
    assert stats["storage_bytes"] == 0
    assert stats["duplicate_photos"] == 0
    assert stats["last_scan_at"] is None
    assert stats["deleted_count"] == 0
    assert stats["space_saved_bytes"] == 0


def test_lifetime_delete_tally_accrues_and_survives_photo_rows(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    doomed = make_textured_image(tmp_path / "doomed.jpg", seed=1)
    make_textured_image(tmp_path / "keeper.jpg", seed=2)
    _index(client, tmp_path)
    assert client.get("/api/stats").json()["deleted_count"] == 0
    doomed_id = next(
        p["id"] for p in client.get("/api/photos").json()["items"] if p["filename"] == "doomed.jpg"
    )
    doomed_size = doomed.stat().st_size

    client.post("/api/quarantine", json={"photo_ids": [doomed_id]})
    client.post("/api/quarantine/delete", json={"photo_ids": [doomed_id], "confirm": True})

    stats = client.get("/api/stats").json()
    assert stats["deleted_count"] == 1
    assert stats["space_saved_bytes"] == doomed_size
    assert stats["photos"] == 1  # only the keeper remains
    # The photo row is gone, but the tally persists from the audit log.
    assert db_session.get(Photo, doomed_id) is None
    assert client.get("/api/stats").json()["deleted_count"] == 1


def test_deleting_more_photos_keeps_a_running_total(client: TestClient, tmp_path: Path) -> None:
    sizes = []
    for i in range(3):
        img = make_textured_image(tmp_path / f"p{i}.jpg", seed=i + 1)
        sizes.append(img.stat().st_size)
    make_textured_image(tmp_path / "keep.jpg", seed=9)
    _index(client, tmp_path)
    ids = {p["filename"]: p["id"] for p in client.get("/api/photos").json()["items"]}

    running_saved = 0
    for i in range(3):
        pid = ids[f"p{i}.jpg"]
        client.post("/api/quarantine", json={"photo_ids": [pid]})
        client.post("/api/quarantine/delete", json={"photo_ids": [pid], "confirm": True})
        running_saved += sizes[i]
        stats = client.get("/api/stats").json()
        assert stats["deleted_count"] == i + 1
        assert stats["space_saved_bytes"] == running_saved
