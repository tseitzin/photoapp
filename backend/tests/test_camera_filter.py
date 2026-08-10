"""Selecting every camera must return every photo.

It did not: the facet list skipped photos whose EXIF names no camera, and SQL
IN never matches NULL, so there was no value that could include them. On a real
5,938-photo library, ticking all 13 cameras returned 5,455.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.images import make_image

MODEL_TAG = 272


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _library(client: TestClient, tmp_path: Path) -> None:
    """Two photos from a camera, three with nothing identifying them."""
    make_image(tmp_path / "a.jpg", exif_fields={MODEL_TAG: "A7 IV"})
    make_image(tmp_path / "b.jpg", exif_fields={MODEL_TAG: "A7 IV"})
    make_image(tmp_path / "c.jpg", exif_fields={MODEL_TAG: "NIKON D70"})
    make_image(tmp_path / "texted.jpg")
    make_image(tmp_path / "screenshot.png")
    _index(client, tmp_path)


def _totals(client: TestClient, cameras: list[str]) -> int:
    params = [("limit", "1")] + [("camera", camera) for camera in cameras]
    return int(client.get("/api/photos", params=params).json()["total"])


def test_selecting_every_camera_returns_every_photo(client: TestClient, tmp_path: Path) -> None:
    """The bug, stated as the promise the UI makes."""
    _library(client, tmp_path)
    facets = client.get("/api/photos/facets").json()["cameras"]

    every = _totals(client, [facet["value"] for facet in facets])

    assert every == client.get("/api/photos?limit=1").json()["total"] == 5


def test_the_camera_facets_account_for_the_whole_library(
    client: TestClient, tmp_path: Path
) -> None:
    _library(client, tmp_path)

    facets = client.get("/api/photos/facets").json()["cameras"]

    assert sum(facet["count"] for facet in facets) == 5


def test_the_no_camera_facet_selects_only_photos_without_one(
    client: TestClient, tmp_path: Path
) -> None:
    _library(client, tmp_path)

    assert _totals(client, [""]) == 2


def test_naming_a_camera_still_excludes_photos_without_one(
    client: TestClient, tmp_path: Path
) -> None:
    """The fix must not quietly widen an ordinary camera filter."""
    _library(client, tmp_path)

    assert _totals(client, ["A7 IV"]) == 2
    assert _totals(client, ["A7 IV", "NIKON D70"]) == 3


def test_a_camera_and_the_no_camera_facet_combine(client: TestClient, tmp_path: Path) -> None:
    _library(client, tmp_path)

    assert _totals(client, ["NIKON D70", ""]) == 3


def test_the_no_camera_facet_is_absent_when_every_photo_has_a_camera(
    client: TestClient, tmp_path: Path
) -> None:
    """No empty bucket cluttering the filter for a tidy library."""
    make_image(tmp_path / "a.jpg", exif_fields={MODEL_TAG: "A7 IV"})
    _index(client, tmp_path)

    values = [facet["value"] for facet in client.get("/api/photos/facets").json()["cameras"]]

    assert values == ["A7 IV"]


def test_the_no_camera_facet_sorts_last(client: TestClient, tmp_path: Path) -> None:
    """It is a catch-all, not a camera — it belongs under the real ones."""
    _library(client, tmp_path)

    values = [facet["value"] for facet in client.get("/api/photos/facets").json()["cameras"]]

    assert values[-1] == ""
    assert values[:2] == ["A7 IV", "NIKON D70"]
