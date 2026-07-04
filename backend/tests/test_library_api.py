from pathlib import Path

from fastapi.testclient import TestClient

from tests.images import make_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def test_folder_tree_rolls_counts_up_to_ancestors(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "top.jpg")
    make_image(tmp_path / "2024/iceland/a.jpg")
    make_image(tmp_path / "2024/iceland/b.jpg")
    make_image(tmp_path / "2024/summer/c.jpg")
    _index(client, tmp_path)

    nodes = {n["path"]: n for n in client.get("/api/folders").json()}

    root = nodes[str(tmp_path)]
    assert root["photo_count"] == 4
    assert root["direct_count"] == 1
    assert root["depth"] == 0
    assert root["has_children"] is True
    year = nodes[str(tmp_path / "2024")]
    assert year["photo_count"] == 3
    assert year["direct_count"] == 0
    assert year["parent_path"] == str(tmp_path)
    iceland = nodes[str(tmp_path / "2024/iceland")]
    assert iceland["photo_count"] == 2
    assert iceland["depth"] == 2
    assert iceland["has_children"] is False


def test_folder_filter_is_recursive(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "outside.jpg")
    make_image(tmp_path / "2024/in1.jpg")
    make_image(tmp_path / "2024/deep/in2.jpg")
    _index(client, tmp_path)

    page = client.get("/api/photos", params={"folder": str(tmp_path / "2024")}).json()

    assert page["total"] == 2
    assert {p["filename"] for p in page["items"]} == {"in1.jpg", "in2.jpg"}


def test_type_filter_merges_jpg_and_jpeg(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "a.jpg")
    make_image(tmp_path / "b.jpeg")
    make_image(tmp_path / "c.png")
    _index(client, tmp_path)

    page = client.get("/api/photos", params={"type": "jpeg"}).json()

    assert page["total"] == 2
    assert {p["filename"] for p in page["items"]} == {"a.jpg", "b.jpeg"}


def test_camera_filter_and_filename_search(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "sony_beach.jpg", exif_fields={272: "A7 IV"})
    make_image(tmp_path / "iphone_beach.jpg", exif_fields={272: "iPhone 15 Pro"})
    make_image(tmp_path / "sony_city.jpg", exif_fields={272: "A7 IV"})
    _index(client, tmp_path)

    by_camera = client.get("/api/photos", params={"camera": "A7 IV"}).json()
    by_search = client.get("/api/photos", params={"q": "beach"}).json()
    combined = client.get("/api/photos", params={"camera": "A7 IV", "q": "beach"}).json()

    assert by_camera["total"] == 2
    assert by_search["total"] == 2
    assert combined["total"] == 1
    assert combined["items"][0]["filename"] == "sony_beach.jpg"


def test_facets_report_type_and_camera_counts(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "a.jpg", exif_fields={272: "A7 IV"})
    make_image(tmp_path / "b.jpeg")
    make_image(tmp_path / "c.png", exif_fields={272: "A7 IV"})
    _index(client, tmp_path)

    facets = client.get("/api/photos/facets").json()

    types = {f["value"]: f["count"] for f in facets["file_types"]}
    assert types == {"jpeg": 2, "png": 1}
    cameras = {f["value"]: f["count"] for f in facets["cameras"]}
    assert cameras == {"A7 IV": 2}


def test_sort_by_name_and_size(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "bbb.jpg", size=(400, 300))
    make_image(tmp_path / "aaa.jpg", size=(1200, 900))
    _index(client, tmp_path)

    by_name = client.get("/api/photos", params={"sort": "name_asc"}).json()
    by_size = client.get("/api/photos", params={"sort": "size_desc"}).json()

    assert [p["filename"] for p in by_name["items"]] == ["aaa.jpg", "bbb.jpg"]
    assert [p["filename"] for p in by_size["items"]] == ["aaa.jpg", "bbb.jpg"]
