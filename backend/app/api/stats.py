from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.stats import compute_stats

router = APIRouter(prefix="/stats")


class StatsRead(BaseModel):
    photos: int
    storage_bytes: int
    folders: int
    missing: int
    duplicate_photos: int
    reclaimable_bytes: int
    last_scan_at: datetime | None
    deleted_count: int
    space_saved_bytes: int


@router.get("")
def get_stats(db: Annotated[Session, Depends(get_db)]) -> StatsRead:
    stats = compute_stats(db)
    return StatsRead(
        photos=stats.photos,
        storage_bytes=stats.storage_bytes,
        folders=stats.folders,
        missing=stats.missing,
        duplicate_photos=stats.duplicate_photos,
        reclaimable_bytes=stats.reclaimable_bytes,
        last_scan_at=stats.last_scan_at,
        deleted_count=stats.deleted_count,
        space_saved_bytes=stats.space_saved_bytes,
    )
