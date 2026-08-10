"""Organize run orchestration: validate, queue the job, poll its state."""

import logging
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.files.organize import (
    UNDATED_DIR,
    OrganizePlan,
    OrganizeSpec,
    SessionFactory,
    build_plan,
    execute_organize,
    validate_spec,
)
from app.files.paths import resolve_lenient
from app.jobs.runner import JobRunner
from app.models import OrganizeRun
from app.models.organize import ACTIVE_ORGANIZE_STATUSES
from app.repositories.organize import OrganizeRunRepository
from app.repositories.photos import PhotoRepository
from app.repositories.scan_roots import ScanRootRepository
from app.repositories.scans import ScanRepository
from app.services.errors import ConflictError, NotFoundError
from app.services.scan_roots import ScanRootService

logger = logging.getLogger(__name__)

# The trailing part of a path that date mode generates. Stripping it turns
# ".../Photos/2019/07" back into the destination the user actually chose.
_DATE_BUCKET = re.compile(rf"/(\d{{4}}/\d{{2}}|{re.escape(UNDATED_DIR)})$")


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

    def library_layout(self) -> list[tuple[str, int]]:
        """Where the library lives today, biggest location first.

        A date tree is reported by the destination it was organized into, not
        by each of its year/month folders — otherwise one library looks like a
        hundred locations. Folders that are not date buckets report themselves,
        which is how loose photos show up.
        """
        totals: Counter[str] = Counter()
        for directory, count in PhotoRepository(self._session).active_directory_counts():
            totals[_DATE_BUCKET.sub("", directory)] += count
        # Biggest first, then by path so equal counts are stable to read.
        return sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))

    def start(self, spec: OrganizeSpec) -> OrganizeRun:
        validate_spec(self._session, spec)  # bad requests 422 here, not as a failed run
        if self._runs.get_active() is not None:
            raise ConflictError("An organize run is already in progress")
        if self._scans.get_active() is not None:
            raise ConflictError("A scan is in progress — wait for it to finish first")
        self._ensure_destination_root(spec.destination)
        run = self._runs.create(spec.as_params(), str(uuid4()))
        factory = self._session_factory
        self._runner.submit(f"organize-{run.id}", lambda: execute_organize(run.id, factory))
        return run

    def _ensure_destination_root(self, destination: str) -> None:
        """Register a destination outside every scan root as a new root, so the
        organized photos stay indexed. The user picked the folder explicitly —
        the app does its own bookkeeping rather than bouncing the request."""
        dest = resolve_lenient(destination)
        repo = ScanRootRepository(self._session)
        if any(dest.is_relative_to(Path(root.path)) for root in repo.list_all()):
            return
        # add_root requires an existing directory (the executor would create it
        # anyway); an empty dir is harmless if the run later fails or is empty.
        dest.mkdir(parents=True, exist_ok=True)
        ScanRootService(repo).add_root(str(dest))
        logger.info("registered organize destination as a scan root: %s", dest)

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
