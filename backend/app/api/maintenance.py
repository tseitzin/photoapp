from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.maintenance import BackfillGpsRequest, BackfillResultRead
from app.services.maintenance import backfill_gps

router = APIRouter(prefix="/maintenance")


@router.post("/backfill-gps")
def run_gps_backfill(
    body: BackfillGpsRequest, db: Annotated[Session, Depends(get_db)]
) -> BackfillResultRead:
    result = backfill_gps(db, after_id=body.after_id, limit=body.limit)
    return BackfillResultRead(
        processed=result.processed,
        updated=result.updated,
        next_after_id=result.next_after_id,
        remaining=result.remaining,
    )
