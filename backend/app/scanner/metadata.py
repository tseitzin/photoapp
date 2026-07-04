"""Decode image bytes and extract dimensions + EXIF metadata.

HEIC/HEIF support comes from pillow-heif; if it is missing, those files fail
decode and are indexed with last_error set rather than crashing the scan.
"""

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PIL import ExifTags, Image

logger = logging.getLogger(__name__)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover - dependency is pinned, but stay graceful
    HEIF_SUPPORTED = False
    logger.warning("pillow-heif not installed; HEIC/HEIF files will fail to decode")

_TAG_MAKE = 271
_TAG_MODEL = 272
_TAG_DATETIME = 306
_TAG_DATETIME_ORIGINAL = 36867
_EXIF_VALUE_MAX_LEN = 256


@dataclass(frozen=True)
class ImageMetadata:
    width: int
    height: int
    captured_at: datetime | None
    camera_make: str | None
    camera_model: str | None
    exif: dict[str, Any]


def _parse_exif_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        # EXIF timestamps carry no timezone; stored naive by design.
        return datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")  # noqa: DTZ007
    except ValueError:
        return None


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().strip("\x00")
    return cleaned or None


def _coerce_json_value(value: object) -> object | None:
    """Return a JSON-storable version of an EXIF value, or None to drop it."""
    if isinstance(value, str):
        cleaned = value.strip("\x00")
        return cleaned[:_EXIF_VALUE_MAX_LEN]
    if isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, tuple | list):
        coerced = [_coerce_json_value(v) for v in value]
        return [c for c in coerced if c is not None][:16]
    # IFDRational and similar numeric wrappers
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _exif_to_dict(exif: Image.Exif) -> dict[str, Any]:
    result: dict[str, Any] = {}
    items: list[tuple[int, object]] = list(exif.items())
    try:
        items += list(exif.get_ifd(ExifTags.IFD.Exif).items())
    except Exception:  # noqa: BLE001 - malformed IFDs must not kill the scan
        logger.debug("unreadable Exif IFD", exc_info=True)
    for tag_id, raw in items:
        name = ExifTags.TAGS.get(tag_id)
        if name is None:
            continue
        value = _coerce_json_value(raw)
        if value is not None:
            result[name] = value
    return result


def extract_metadata(data: bytes) -> ImageMetadata:
    """Decode ``data`` and return metadata. Raises on undecodable input."""
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        exif = image.getexif()
        try:
            exif_ifd: dict[int, object] = dict(exif.get_ifd(ExifTags.IFD.Exif))
        except Exception:  # noqa: BLE001
            exif_ifd = {}

        captured_at = _parse_exif_datetime(
            exif_ifd.get(_TAG_DATETIME_ORIGINAL)
        ) or _parse_exif_datetime(exif.get(_TAG_DATETIME))

        return ImageMetadata(
            width=width,
            height=height,
            captured_at=captured_at,
            camera_make=_clean_str(exif.get(_TAG_MAKE)),
            camera_model=_clean_str(exif.get(_TAG_MODEL)),
            exif=_exif_to_dict(exif),
        )
