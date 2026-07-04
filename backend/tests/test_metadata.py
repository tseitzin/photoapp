from datetime import datetime
from pathlib import Path

import pytest

from app.scanner.metadata import extract_metadata
from tests.images import make_image

TAG_MAKE, TAG_MODEL, TAG_DATETIME = 271, 272, 306
TAG_DATETIME_ORIGINAL = 36867


def _bytes_of(path: Path) -> bytes:
    return path.read_bytes()


def test_extracts_dimensions_from_a_plain_image(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "p.jpg", size=(120, 80))

    meta = extract_metadata(_bytes_of(photo))

    assert (meta.width, meta.height) == (120, 80)
    assert meta.captured_at is None
    assert meta.camera_make is None


def test_extracts_camera_and_capture_date_from_exif(tmp_path: Path) -> None:
    photo = make_image(
        tmp_path / "p.jpg",
        exif_fields={TAG_MAKE: "Apple", TAG_MODEL: "iPhone 15 Pro"},
        exif_ifd_fields={TAG_DATETIME_ORIGINAL: "2024:05:01 09:30:00"},
    )

    meta = extract_metadata(_bytes_of(photo))

    assert meta.camera_make == "Apple"
    assert meta.camera_model == "iPhone 15 Pro"
    assert meta.captured_at == datetime(2024, 5, 1, 9, 30)  # noqa: DTZ001


def test_falls_back_to_datetime_tag_when_original_is_absent(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "p.jpg", exif_fields={TAG_DATETIME: "2023:12:24 18:00:00"})

    meta = extract_metadata(_bytes_of(photo))

    assert meta.captured_at == datetime(2023, 12, 24, 18, 0)  # noqa: DTZ001


def test_garbled_exif_datetime_yields_none_not_a_crash(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "p.jpg", exif_fields={TAG_DATETIME: "not a date"})

    assert extract_metadata(_bytes_of(photo)).captured_at is None


def test_exif_dict_is_json_serializable(tmp_path: Path) -> None:
    import json

    photo = make_image(
        tmp_path / "p.jpg",
        exif_fields={TAG_MAKE: "Sony", TAG_DATETIME: "2024:01:01 00:00:00"},
    )

    meta = extract_metadata(_bytes_of(photo))

    json.dumps(meta.exif)
    assert meta.exif["Make"] == "Sony"


def test_undecodable_bytes_raise(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017 - any decode failure is acceptable
        extract_metadata(b"definitely not an image")


def test_png_and_webp_decode(tmp_path: Path) -> None:
    for name in ("p.png", "p.webp"):
        meta = extract_metadata(_bytes_of(make_image(tmp_path / name, size=(30, 20))))
        assert (meta.width, meta.height) == (30, 20)
