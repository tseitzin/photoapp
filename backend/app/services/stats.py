from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Photo, Scan


@dataclass(frozen=True)
class LibraryStats:
    photos: int
    storage_bytes: int
    folders: int
    missing: int
    duplicate_photos: int
    reclaimable_bytes: int
    last_scan_at: datetime | None


def compute_stats(session: Session) -> LibraryStats:
    active = Photo.status == "active"

    photos = session.scalar(select(func.count()).select_from(Photo).where(active)) or 0
    storage = session.scalar(select(func.coalesce(func.sum(Photo.size_bytes), 0)).where(active))
    folders = (
        session.scalar(
            select(func.count(func.distinct(func.regexp_replace(Photo.path, r"/[^/]*$", ""))))
            .select_from(Photo)
            .where(active)
        )
        or 0
    )
    missing = (
        session.scalar(select(func.count()).select_from(Photo).where(Photo.status == "missing"))
        or 0
    )

    # Exact-duplicate preview from sha256 (formal groups arrive in Phase 5):
    # in each same-hash group, all but one copy are redundant.
    groups = (
        select(
            (func.count() - 1).label("extra"),
            ((func.count() - 1) * func.max(Photo.size_bytes)).label("reclaimable"),
        )
        .where(active, Photo.sha256.is_not(None))
        .group_by(Photo.sha256)
        .having(func.count() > 1)
        .subquery()
    )
    duplicate_photos, reclaimable = session.execute(
        select(
            func.coalesce(func.sum(groups.c.extra), 0),
            func.coalesce(func.sum(groups.c.reclaimable), 0),
        )
    ).one()

    last_scan_at = session.scalar(
        select(func.max(Scan.finished_at)).where(Scan.status == "completed")
    )

    return LibraryStats(
        photos=photos,
        storage_bytes=int(storage or 0),
        folders=folders,
        missing=missing,
        duplicate_photos=int(duplicate_photos),
        reclaimable_bytes=int(reclaimable),
        last_scan_at=last_scan_at,
    )
