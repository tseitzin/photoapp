import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import APP_VERSION
from app.db.session import get_db
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    database: Literal["ok", "unavailable"] = "ok"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("health check: database unreachable", exc_info=True)
        database = "unavailable"
    return HealthResponse(status="ok", database=database, version=APP_VERSION)
