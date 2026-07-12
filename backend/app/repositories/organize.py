from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OrganizeRun
from app.models.organize import ACTIVE_ORGANIZE_STATUSES


class OrganizeRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, params: dict[str, Any], batch_id: str) -> OrganizeRun:
        run = OrganizeRun(params=params, batch_id=batch_id)
        self._session.add(run)
        self._session.commit()
        self._session.refresh(run)
        return run

    def get(self, run_id: int) -> OrganizeRun | None:
        return self._session.get(OrganizeRun, run_id)

    def get_active(self) -> OrganizeRun | None:
        return self._session.scalar(
            select(OrganizeRun).where(OrganizeRun.status.in_(ACTIVE_ORGANIZE_STATUSES)).limit(1)
        )

    def list_recent(self, limit: int = 5) -> Sequence[OrganizeRun]:
        return self._session.scalars(
            select(OrganizeRun).order_by(OrganizeRun.id.desc()).limit(limit)
        ).all()

    def mark_running(self, run: OrganizeRun) -> None:
        run.status = "running"
        run.started_at = datetime.now(UTC)
        self._session.commit()

    def mark_finished(self, run: OrganizeRun, status: str, message: str | None = None) -> None:
        run.status = status
        run.message = message
        run.finished_at = datetime.now(UTC)
        self._session.commit()

    def commit(self) -> None:
        self._session.commit()
