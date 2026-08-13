"""Decode image bytes and extract dimensions + EXIF metadata.

HEIC/HEIF support comes from pillow-heif; if it is missing, those files fail
decode and are indexed with last_error set rather than crashing the scan.
"""

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PIL import ExifTags, Image, ImageOps

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
# Tags within the GPS IFD (ExifTags.IFD.GPSInfo).
_GPS_LAT_REF = 1
_GPS_LAT = 2
_GPS_LON_REF = 3
_GPS_LON = 4


@dataclass(frozen=True)
class ImageMetadata:
    width: int
    height: int
    captured_at: datetime | None
    camera_make: str | None
    camera_model: str | None
    latitude: float | None
    longitude: float | None
    exif: dict[str, Any]


def _parse_exif_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        # EXIF timestamps carry no timezone; stored naive by design.
        return datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")  # noqa: DTZ007
    except ValueError:
        return None


def _without_nulls(value: str) -> str:
    """Remove every NUL, wherever it sits in the string.

    Postgres stores no \\x00 in `text` or `jsonb`, at any position, and one that
    slips through fails the whole INSERT batch — which fails the scan, after it
    has already indexed thousands of files. A real import died this way: a
    Samsung camera pads the fixed-width ImageDescription with NULs and *then*
    spaces, so `.strip("\\x00")` found a space at the end and removed nothing.

    Stripping is the wrong tool regardless — a NUL in the middle of a value is
    just as fatal and no amount of end-trimming reaches it.
    """
    return value.replace("\x00", "")


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = _without_nulls(value).strip()
    return cleaned or None


def _coerce_json_value(value: object) -> object | None:
    """Return a JSON-storable version of an EXIF value, or None to drop it."""
    if isinstance(value, str):
        return _without_nulls(value)[:_EXIF_VALUE_MAX_LEN]
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


def _dms_to_decimal(dms: object, ref: object, negative_ref: str) -> float | None:
    """Degrees/minutes/seconds rationals -> signed decimal degrees, or None."""
    if not isinstance(dms, tuple | list) or len(dms) != 3:
        return None
    try:
        value = float(dms[0]) + float(dms[1]) / 60 + float(dms[2]) / 3600
    except (TypeError, ValueError, ZeroDivisionError):  # 0/0 IFDRational raises too
        return None
    if isinstance(ref, str) and ref.strip().upper() == negative_ref:
        value = -value
    return value


def _parse_gps(exif: Image.Exif) -> tuple[float | None, float | None]:
    """(latitude, longitude) from the GPS IFD — both or neither, range-checked."""
    try:
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    except Exception:  # noqa: BLE001 - malformed IFDs must not kill the scan
        logger.debug("unreadable GPS IFD", exc_info=True)
        return None, None
    latitude = _dms_to_decimal(gps.get(_GPS_LAT), gps.get(_GPS_LAT_REF), "S")
    longitude = _dms_to_decimal(gps.get(_GPS_LON), gps.get(_GPS_LON_REF), "W")
    if latitude is None or longitude is None or abs(latitude) > 90 or abs(longitude) > 180:
        return None, None
    return latitude, longitude


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


def read_metadata(image: Image.Image, width: int, height: int) -> ImageMetadata:
    """Extract metadata from an already-decoded image.

    Width/height are passed in so callers can supply orientation-corrected
    dimensions (what the user actually sees).
    """
    exif = image.getexif()
    try:
        exif_ifd: dict[int, object] = dict(exif.get_ifd(ExifTags.IFD.Exif))
    except Exception:  # noqa: BLE001
        exif_ifd = {}

    captured_at = _parse_exif_datetime(
        exif_ifd.get(_TAG_DATETIME_ORIGINAL)
    ) or _parse_exif_datetime(exif.get(_TAG_DATETIME))
    latitude, longitude = _parse_gps(exif)

    return ImageMetadata(
        width=width,
        height=height,
        captured_at=captured_at,
        camera_make=_clean_str(exif.get(_TAG_MAKE)),
        camera_model=_clean_str(exif.get(_TAG_MODEL)),
        latitude=latitude,
        longitude=longitude,
        # GPS tags stay out of the JSONB dump; the columns are the contract.
        exif=_exif_to_dict(exif),
    )


def extract_metadata(data: bytes) -> ImageMetadata:
    """Decode ``data`` and return metadata. Raises on undecodable input."""
    with Image.open(io.BytesIO(data)) as image:
        oriented = ImageOps.exif_transpose(image)
        return read_metadata(image, oriented.width, oriented.height)
