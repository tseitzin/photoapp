"""Scan orchestration: walk roots, process files in batches, persist progress.

Progress counters and batch results commit together, so the Scan row is always
a consistent snapshot for the polling UI, and an interrupted scan loses at most
one batch (a rescan skips everything already persisted — that is the
resumability model).
"""

import logging
import os
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.jobs.runner import JobRunner
from app.models import Photo, Scan, ScanError, ScanRoot
from app.models.scan import ACTIVE_SCAN_STATUSES
from app.repositories.photos import ExistingFile, PhotoRepository
from app.repositories.scan_roots import ScanRootRepository
from app.repositories.scans import ScanRepository
from app.scanner.discovery import DiscoveredFile, DiscoveryError, walk_root
from app.scanner.processing import ProcessedFile, process_file
from app.services.errors import ConflictError, NotFoundError, ValidationFailedError

logger = logging.getLogger(__name__)

_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heif",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}

SessionFactory = Callable[[], Session]
BatchProcessor = Callable[[list[str]], list[ProcessedFile]]


class ScanService:
    """Request-scoped operations on scans."""

    def __init__(
        self, session: Session, runner: JobRunner, session_factory: SessionFactory
    ) -> None:
        self._scans = ScanRepository(session)
        self._roots = ScanRootRepository(session)
        self._runner = runner
        self._session_factory = session_factory

    def start(self, root_ids: list[int] | None) -> Scan:
        if self._scans.get_active() is not None:
            raise ConflictError("A scan is already in progress")
        if root_ids:
            unknown = [i for i in root_ids if self._roots.get(i) is None]
            if unknown:
                raise ValidationFailedError(f"Unknown scan root ids: {unknown}")
        elif not any(root.enabled for root in self._roots.list_all()):
            raise ValidationFailedError("No enabled scan roots configured")

        scan = self._scans.create(root_ids)
        factory = self._session_factory
        self._runner.submit(f"scan-{scan.id}", lambda: execute_scan(scan.id, factory))
        return scan

    def get(self, scan_id: int) -> Scan:
        scan = self._scans.get(scan_id)
        if scan is None:
            raise NotFoundError(f"Scan {scan_id} not found")
        return scan

    def list_recent(self, limit: int) -> list[Scan]:
        return list(self._scans.list_recent(limit))

    def cancel(self, scan_id: int) -> Scan:
        scan = self.get(scan_id)
        if scan.status not in ACTIVE_SCAN_STATUSES:
            raise ConflictError(f"Scan {scan_id} is already {scan.status}")
        scan.status = "cancelled"
        self._scans.commit()
        return scan

    def errors(self, scan_id: int, limit: int, offset: int) -> tuple[list[ScanError], int]:
        self.get(scan_id)
        items, total = self._scans.list_errors(scan_id, limit=limit, offset=offset)
        return list(items), total


def execute_scan(scan_id: int, session_factory: SessionFactory) -> None:
    """Background job body. Opens its own session; safe to run in any runner."""
    settings = get_settings()
    with session_factory() as session:
        scans = ScanRepository(session)
        photos = PhotoRepository(session)
        scan = scans.get(scan_id)
        if scan is None:  # pragma: no cover - job outliving its row is a bug
            logger.error("scan %s vanished before execution", scan_id)
            return
        if scan.status == "cancelled":
            scans.mark_finished(scan, "cancelled")
            return

        roots = _roots_for(session, scan)
        scans.mark_running(scan)
        try:
            with _batch_processor(settings.scan_workers) as run_batch:
                for root in roots:
                    cancelled = _scan_root(
                        session, scans, photos, scan, root, run_batch, settings.scan_batch_size
                    )
                    if cancelled:
                        scans.mark_finished(scan, "cancelled")
                        logger.info("scan %s cancelled", scan_id)
                        return
            scans.mark_finished(scan, "completed")
            logger.info(
                "scan %s completed: %s found, %s added, %s errors",
                scan_id,
                scan.files_found,
                scan.files_added,
                scan.error_count,
            )
        except Exception as exc:
            logger.exception("scan %s failed", scan_id)
            session.rollback()
            scans.mark_finished(scan, "failed", message=f"{type(exc).__name__}: {exc}")


def _roots_for(session: Session, scan: Scan) -> list[ScanRoot]:
    repo = ScanRootRepository(session)
    if scan.root_ids:
        return [root for root in repo.list_all() if root.id in scan.root_ids]
    return [root for root in repo.list_all() if root.enabled]


@contextmanager
def _batch_processor(workers: int) -> Iterator[BatchProcessor]:
    """Serial when workers=0; otherwise a process pool for CPU-bound decode/hash."""
    if workers == 0:
        yield lambda paths: [process_file(path) for path in paths]
        return
    max_workers = workers if workers > 0 else max(1, (os.cpu_count() or 2) - 1)
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        yield lambda paths: list(pool.map(process_file, paths, chunksize=8))


def _scan_root(
    session: Session,
    scans: ScanRepository,
    photos: PhotoRepository,
    scan: Scan,
    root: ScanRoot,
    run_batch: BatchProcessor,
    batch_size: int,
) -> bool:
    """Walk one root. Returns True if the scan was cancelled mid-walk."""
    existing = photos.index_for_root(root.id)
    pending: list[str] = []

    def flush() -> bool:
        if pending:
            for result in run_batch(pending):
                _apply_result(session, scans, scan, root, existing, result)
            scan.current_path = pending[-1]
            pending.clear()
        session.commit()
        return scans.current_status(scan.id) == "cancelled"

    for item in walk_root(Path(root.path)):
        if isinstance(item, DiscoveryError):
            scans.add_error(scan, item.path, item.error)
            continue
        scan.files_found += 1
        if _is_unchanged(existing.get(item.path), item):
            scan.files_unchanged += 1
            scan.files_processed += 1
            continue
        pending.append(item.path)
        if len(pending) >= batch_size and flush():
            return True
    return flush()


def _is_unchanged(known: ExistingFile | None, item: DiscoveredFile) -> bool:
    return (
        known is not None
        and known.status == "active"
        and known.size_bytes == item.size_bytes
        and known.mtime_ns == item.mtime_ns
    )


def _apply_result(
    session: Session,
    scans: ScanRepository,
    scan: Scan,
    root: ScanRoot,
    existing: dict[str, ExistingFile],
    result: ProcessedFile,
) -> None:
    if result.error is not None:
        scans.add_error(scan, result.path, result.error)
    if not result.readable:
        # Bytes were unreadable: nothing trustworthy to persist about content.
        scan.files_processed += 1
        return

    known = existing.get(result.path)
    ext = Path(result.path).suffix.lower().lstrip(".")
    meta = result.metadata
    fields = {
        "size_bytes": result.size_bytes,
        "mtime_ns": result.mtime_ns,
        "sha256": result.sha256,
        "width": meta.width if meta else None,
        "height": meta.height if meta else None,
        "captured_at": meta.captured_at if meta else None,
        "camera_make": meta.camera_make if meta else None,
        "camera_model": meta.camera_model if meta else None,
        "exif": meta.exif if meta else None,
        "last_error": result.error,
        "status": "active",
    }
    if known is None:
        session.add(
            Photo(
                root_id=root.id,
                path=result.path,
                filename=Path(result.path).name,
                ext=ext,
                mime=_MIME_BY_EXT.get(ext, "application/octet-stream"),
                **fields,
            )
        )
        scan.files_added += 1
    else:
        photo = session.get(Photo, known.photo_id)
        if photo is not None:
            for key, value in fields.items():
                setattr(photo, key, value)
        scan.files_changed += 1
    scan.files_processed += 1
