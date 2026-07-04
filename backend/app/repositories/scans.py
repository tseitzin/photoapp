from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Scan, ScanError
from app.models.scan import ACTIVE_SCAN_STATUSES


class ScanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, root_ids: list[int] | None) -> Scan:
        scan = Scan(root_ids=root_ids)
        self._session.add(scan)
        self._session.commit()
        self._session.refresh(scan)
        return scan

    def get(self, scan_id: int) -> Scan | None:
        return self._session.get(Scan, scan_id)

    def get_active(self) -> Scan | None:
        return self._session.scalar(
            select(Scan).where(Scan.status.in_(ACTIVE_SCAN_STATUSES)).limit(1)
        )

    def list_recent(self, limit: int = 20) -> Sequence[Scan]:
        return self._session.scalars(select(Scan).order_by(Scan.id.desc()).limit(limit)).all()

    def current_status(self, scan_id: int) -> str | None:
        """Fresh read (post-commit) so a cancel from another session is seen."""
        return self._session.scalar(select(Scan.status).where(Scan.id == scan_id))

    def mark_running(self, scan: Scan) -> None:
        scan.status = "running"
        scan.started_at = datetime.now(UTC)
        self._session.commit()

    def mark_finished(self, scan: Scan, status: str, message: str | None = None) -> None:
        scan.status = status
        scan.message = message
        scan.finished_at = datetime.now(UTC)
        scan.current_path = None
        self._session.commit()

    def add_error(self, scan: Scan, path: str, error: str) -> None:
        self._session.add(ScanError(scan_id=scan.id, path=path, error=error))
        scan.error_count += 1

    def list_errors(self, scan_id: int, limit: int, offset: int) -> tuple[Sequence[ScanError], int]:
        total = self._session.scalar(
            select(func.count()).select_from(ScanError).where(ScanError.scan_id == scan_id)
        )
        items = self._session.scalars(
            select(ScanError)
            .where(ScanError.scan_id == scan_id)
            .order_by(ScanError.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return items, total or 0

    def commit(self) -> None:
        self._session.commit()
