"""Organize run orchestration: validate, queue the job, poll its state."""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.files.organize import (
    OrganizePlan,
    OrganizeSpec,
    SessionFactory,
    build_plan,
    execute_organize,
    validate_spec,
)
from app.jobs.runner import JobRunner
from app.models import OrganizeRun
from app.models.organize import ACTIVE_ORGANIZE_STATUSES
from app.repositories.organize import OrganizeRunRepository
from app.repositories.scans import ScanRepository
from app.services.errors import ConflictError, NotFoundError

logger = logging.getLogger(__name__)


class OrganizeService:
    """Request-scoped operations on organize runs."""

    def __init__(
        self, session: Session, runner: JobRunner, session_factory: SessionFactory
    ) -> None:
        self._session = session
        self._runs = OrganizeRunRepository(session)
        self._scans = ScanRepository(session)
        self._runner = runner
        self._session_factory = session_factory

    def preview(self, spec: OrganizeSpec) -> OrganizePlan:
        return build_plan(self._session, spec)

    def start(self, spec: OrganizeSpec) -> OrganizeRun:
        validate_spec(self._session, spec)  # bad requests 422 here, not as a failed run
        if self._runs.get_active() is not None:
            raise ConflictError("An organize run is already in progress")
        if self._scans.get_active() is not None:
            raise ConflictError("A scan is in progress — wait for it to finish first")
        run = self._runs.create(spec.as_params(), str(uuid4()))
        factory = self._session_factory
        self._runner.submit(f"organize-{run.id}", lambda: execute_organize(run.id, factory))
        return run

    def get(self, run_id: int) -> OrganizeRun:
        run = self._runs.get(run_id)
        if run is None:
            raise NotFoundError(f"Organize run {run_id} not found")
        return run

    def list_recent(self, limit: int) -> list[OrganizeRun]:
        return list(self._runs.list_recent(limit))


def recover_interrupted_runs(session: Session) -> int:
    """Mark organize runs left pending/running by a crash or restart as failed.

    Files already moved are consistent with the index (chunked commits); a
    rescan reconciles anything in the final uncommitted chunk via sha256
    move detection.
    """
    stale = session.scalars(
        select(OrganizeRun).where(OrganizeRun.status.in_(ACTIVE_ORGANIZE_STATUSES))
    ).all()
    for run in stale:
        run.status = "failed"
        run.message = (
            "Interrupted by an app restart. Moved files are safe; run a scan to "
            "reconcile, then organize again."
        )
        run.finished_at = datetime.now(UTC)
    session.commit()
    if stale:
        logger.warning("recovered %d interrupted organize run(s)", len(stale))
    return len(stale)
