from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.repositories.photos import PhotoRepository
from tests.images import make_image


def _index_photos(client: TestClient, root: Path, count: int) -> None:
    for i in range(count):
        make_image(root / f"photo_{i:02d}.jpg", color=f"hsl({i * 25}, 60%, 50%)")
    response = client.post("/api/scan-roots", json={"path": str(root)})
    assert response.status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def test_lists_indexed_photos_with_pagination(client: TestClient, tmp_path: Path) -> None:
    _index_photos(client, tmp_path, 5)

    page = client.get("/api/photos", params={"limit": 2, "offset": 0}).json()

    assert page["total"] == 5
    assert len(page["items"]) == 2
    rest = client.get("/api/photos", params={"limit": 200, "offset": 2}).json()
    assert len(rest["items"]) == 3
    all_ids = {p["id"] for p in page["items"]} | {p["id"] for p in rest["items"]}
    assert len(all_ids) == 5


def test_listing_photos_leaves_the_exif_blob_on_the_server(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """exif is ~1.3 KB inline per row and no list response exposes it.

    Deferring it is only a win if nothing then touches the attribute — that
    would trade one wide query for a lazy load per row.
    """
    make_image(tmp_path / "one.jpg", exif_fields={271: "Sony"})
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    client.post("/api/scans", json={})

    items, _ = PhotoRepository(db_session).list_page(limit=10, offset=0)

    assert items
    assert "exif" in inspect(items[0]).unloaded
    assert "exif" not in client.get("/api/photos").json()["items"][0]


def test_photo_detail_includes_hash_and_exif(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "one.jpg", exif_fields={271: "Sony"})
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    client.post("/api/scans", json={})
    photo_id = client.get("/api/photos").json()["items"][0]["id"]

    detail = client.get(f"/api/photos/{photo_id}").json()

    assert detail["sha256"] is not None
    assert detail["exif"]["Make"] == "Sony"
    assert detail["camera_make"] == "Sony"


def test_unknown_photo_returns_404(client: TestClient) -> None:
    assert client.get("/api/photos/424242").status_code == 404


def test_status_filter_excludes_missing_photos(client: TestClient, tmp_path: Path) -> None:
    gone = make_image(tmp_path / "gone.jpg", color="red")
    make_image(tmp_path / "here.jpg", color="green")
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    client.post("/api/scans", json={})
    gone.unlink()
    client.post("/api/scans", json={})

    active = client.get("/api/photos", params={"status": "active"}).json()
    everything = client.get("/api/photos").json()

    assert everything["total"] == 2
    assert active["total"] == 1
    assert active["items"][0]["filename"] == "here.jpg"
