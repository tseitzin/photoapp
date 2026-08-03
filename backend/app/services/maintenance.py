"""One-off maintenance operations, currently just the GPS backfill.

Rescans skip unchanged files, so photos indexed before GPS extraction existed
would never gain coordinates on their own. The backfill reads only the EXIF
header of each candidate (no decode, no hashing, no thumbnails) and walks the
library in id-cursor chunks; repeat calls with the returned cursor until
next_after_id is null.

It also names the nearest place for every coordinate it finds, batched — one
reverse-geocode call per chunk rather than per photo.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image
from sqlalchemy.orm import Session

from app.geo.places import lookup_places

# Importing scanner.metadata also registers the HEIF opener, so HEIC EXIF works.
from app.repositories.photos import PhotoRepository
from app.scanner.metadata import _parse_gps

if TYPE_CHECKING:
    from app.models import Photo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillResult:
    processed: int
    updated: int
    next_after_id: int | None
    remaining: int


def backfill_gps(session: Session, after_id: int = 0, limit: int = 1000) -> BackfillResult:
    photos = PhotoRepository(session)
    candidates = photos.gps_backfill_candidates(after_id, limit)
    found: list[tuple[Photo, float, float]] = []
    for photo in candidates:
        try:
            with Image.open(photo.path) as image:
                latitude, longitude = _parse_gps(image.getexif())
        except Exception:  # noqa: BLE001 - unreadable files are simply skipped
            continue
        if latitude is not None and longitude is not None:
            photo.latitude = latitude
            photo.longitude = longitude
            found.append((photo, latitude, longitude))

    # One geocode call for the whole chunk — the tree lookup is vectorised, so
    # batching is far cheaper than a call per photo.
    for (photo, _, _), place in zip(
        found, lookup_places([(la, lo) for _, la, lo in found]), strict=True
    ):
        photo.city = place.city if place else None
        photo.region = place.region if place else None
        photo.country = place.country if place else None
        photo.place_distance_km = place.distance_km if place else None

    updated = len(found)
    session.commit()

    last_id = candidates[-1].id if candidates else None
    has_more = len(candidates) == limit and last_id is not None
    remaining = photos.count_gps_backfill_remaining(last_id) if has_more and last_id else 0
    logger.info(
        "gps backfill: %d processed, %d updated, %d remaining",
        len(candidates),
        updated,
        remaining,
    )
    return BackfillResult(
        processed=len(candidates),
        updated=updated,
        next_after_id=last_id if has_more else None,
        remaining=remaining,
    )
