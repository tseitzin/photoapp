"""GPS extraction from EXIF: decimal conversion, hemisphere signs, resilience."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.scanner.metadata import extract_metadata
from tests.images import gps_exif, make_image


def _metadata_for(path: Path):
    return extract_metadata(path.read_bytes())


def test_extracts_decimal_coordinates_from_gps_exif(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "geo.jpg", gps_ifd_fields=gps_exif(47.6038, 9.5601))

    meta = _metadata_for(photo)

    assert meta.latitude == pytest.approx(47.6038, abs=1e-4)
    assert meta.longitude == pytest.approx(9.5601, abs=1e-4)


def test_southern_and_western_hemispheres_are_negative(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "geo.jpg", gps_ifd_fields=gps_exif(-33.8688, -70.6693))

    meta = _metadata_for(photo)

    assert meta.latitude == pytest.approx(-33.8688, abs=1e-4)
    assert meta.longitude == pytest.approx(-70.6693, abs=1e-4)


def test_photos_without_gps_have_no_coordinates(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "plain.jpg", exif_fields={272: "Canon"})

    meta = _metadata_for(photo)

    assert meta.latitude is None
    assert meta.longitude is None


def test_malformed_gps_yields_none_not_a_crash(tmp_path: Path) -> None:
    # Latitude present but not a 3-tuple of rationals; longitude missing entirely.
    photo = make_image(tmp_path / "broken.jpg", gps_ifd_fields={1: "N", 2: (12.0,)})

    meta = _metadata_for(photo)

    assert meta.latitude is None
    assert meta.longitude is None


def test_gps_is_both_coordinates_or_neither(tmp_path: Path) -> None:
    photo = make_image(
        tmp_path / "half.jpg", gps_ifd_fields={1: "N", 2: (47.0, 30.0, 0.0)}
    )  # no longitude

    meta = _metadata_for(photo)

    assert meta.latitude is None
    assert meta.longitude is None


def test_gps_tags_stay_out_of_the_exif_json(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "geo.jpg", gps_ifd_fields=gps_exif(47.6, 9.56))

    meta = _metadata_for(photo)

    assert "GPSLatitude" not in meta.exif


def test_scan_persists_coordinates_on_photos(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "geo.jpg", gps_ifd_fields=gps_exif(47.6038, 9.5601))
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202

    photo = client.get("/api/photos").json()["items"][0]

    assert photo["latitude"] == pytest.approx(47.6038, abs=1e-4)
    assert photo["longitude"] == pytest.approx(9.5601, abs=1e-4)


def test_written_gps_exif_round_trips_through_pillow(tmp_path: Path) -> None:
    """Guards the test helper itself: the GPS IFD written by gps_exif is readable."""
    photo = make_image(tmp_path / "geo.jpg", gps_ifd_fields=gps_exif(1.5, -2.25))

    with Image.open(photo) as image:
        gps = image.getexif().get_ifd(0x8825)

    assert gps[1] == "N" and gps[3] == "W"
