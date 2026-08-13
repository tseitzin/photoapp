"""Scan orchestration: walk roots, process files in batches, persist progress.

Progress counters and batch results commit together, so the Scan row is always
a consistent snapshot for the polling UI, and an interrupted scan loses at most
one batch (a rescan skips everything already persisted — that is the
resumability model).
"""

import logging
import os
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Event, Semaphore, Thread

from opentelemetry.trace import Span
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.telemetry import add_attributes, record_failure, span
from app.geo.places import lookup_place
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


@dataclass
class TouchedPhotos:
    """Which photos a scan altered, for the bounded duplicate rebuild.

    Additions are collected as paths because a new row has no id until it is
    flushed, and `path` is unique. They are resolved after the move/missing pass,
    which can delete an added row: `_record_move` keeps the original photo and
    retargets it at the new path, so resolving by path then yields whichever row
    actually survived.

    Moves are deliberately absent — a move changes only where the bytes live,
    and duplicate groups are derived from content.
    """

    added_paths: set[str] = field(default_factory=set)
    ids: set[int] = field(default_factory=set)

    def resolve(self, session: Session) -> set[int]:
        resolved = set(self.ids)
        paths = sorted(self.added_paths)
        for start in range(0, len(paths), 5_000):
            resolved.update(
                session.scalars(
                    select(Photo.id).where(Photo.path.in_(paths[start : start + 5_000]))
                ).all()
            )
        return resolved


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
        # One span for the whole job, deliberately coarse: a span per file
        # would be ~4,500 per scan, re-encoding what the counters already hold.
        with span("scan", scan_id=scan_id, roots=len(roots)) as scan_span:
            try:
                per_root: list[tuple[dict[str, ExistingFile], set[str]]] = []
                added_by_sha: dict[str, list[str]] = {}
                touched = TouchedPhotos()
                with _batch_processor(settings.scan_workers) as run_batch:
                    for root in roots:
                        cancelled, existing, seen = _scan_root(
                            session,
                            scans,
                            photos,
                            scan,
                            root,
                            run_batch,
                            settings.scan_batch_size,
                            added_by_sha,
                            touched,
                        )
                        if cancelled:
                            scans.mark_finished(scan, "cancelled")
                            logger.info("scan %s cancelled", scan_id)
                            return
                        per_root.append((existing, seen))
                _reconcile_moves_and_missing(session, scan, per_root, added_by_sha, touched)
                # Duplicate groups derive from photo state — refresh them while the
                # scan is still "running" so the UI never sees stale groups. When
                # the scan touched nothing, that state is unchanged and so are the
                # groups; the rebuild is the most expensive part of a scan, so a
                # re-scan that finds no changes should cost nothing.
                if _changed_anything(scan):
                    _refresh_duplicate_groups(session, scan_id, touched, scan_span)
                else:
                    logger.info(
                        "scan %s changed nothing; keeping existing duplicate groups", scan_id
                    )
                scans.mark_finished(scan, "completed")
                _record_progress(scan_span, scan)
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
                # Counts go on the span even here — especially here. A crash
                # after indexing 11,500 files and one after indexing none are
                # very different problems, and a span that reports zeros for
                # both makes the trace useless exactly when it is needed. The
                # numbers survive the rollback: they are read off the in-memory
                # Scan row, which mark_finished has already committed.
                _record_progress(scan_span, scan)
                record_failure(scan_span, exc)


def _place_fields(latitude: float | None, longitude: float | None) -> dict[str, object]:
    """Nearest-place columns for a coordinate, empty when there isn't one."""
    place = lookup_place(latitude, longitude)
    if place is None:
        return {"city": None, "region": None, "country": None, "place_distance_km": None}
    return {
        "city": place.city,
        "region": place.region,
        "country": place.country,
        "place_distance_km": place.distance_km,
    }


# Above this share of the active library, the bounded pass stops paying: its
# subgraph approaches the whole library anyway, and the full derivation gets
# there in one pass instead of one plus the candidate lookups that bound it.
_FULL_REBUILD_TOUCHED_SHARE = 0.25


def _refresh_duplicate_groups(
    session: Session, scan_id: int, touched: TouchedPhotos, scan_span: Span
) -> None:
    """Re-derive duplicate groups, bounded to what this scan changed.

    The full pass costs O(n^2/64) distance checks over the whole library, so an
    import of a few hundred photos into a large one used to pay for every photo
    already indexed. Falls back to the full pass when the scan rewrote enough of
    the library that bounding it saves nothing.
    """
    from app.services.duplicates import rebuild_duplicate_groups, rebuild_groups_for

    touched_ids = touched.resolve(session)
    active = session.scalar(select(func.count()).select_from(Photo).where(Photo.status == "active"))
    share = len(touched_ids) / active if active else 1.0

    if not touched_ids or share > _FULL_REBUILD_TOUCHED_SHARE:
        add_attributes(scan_span, dedupe_pass="full", dedupe_touched=len(touched_ids))
        logger.info(
            "scan %s: full duplicate rebuild (%d of %d active photos touched)",
            scan_id,
            len(touched_ids),
            active or 0,
        )
        rebuild_duplicate_groups(session)
        return

    add_attributes(scan_span, dedupe_pass="bounded", dedupe_touched=len(touched_ids))
    rebuild_groups_for(session, touched_ids)


def _record_progress(scan_span: Span, scan: Scan) -> None:
    """Put how far the scan got on its span, whether or not it finished."""
    add_attributes(
        scan_span,
        files_found=scan.files_found,
        files_added=scan.files_added,
        files_changed=scan.files_changed,
        files_missing=scan.files_missing,
        files_moved=scan.files_moved,
        errors=scan.error_count,
    )


def _changed_anything(scan: Scan) -> bool:
    """Did this scan alter the active photo set at all?

    Derived duplicate groups are a pure function of the active photo rows, so
    if none were added, changed, moved or lost, the groups cannot differ.
    """
    return bool(scan.files_added or scan.files_changed or scan.files_missing or scan.files_moved)


def _roots_for(session: Session, scan: Scan) -> list[ScanRoot]:
    repo = ScanRootRepository(session)
    if scan.root_ids:
        return [root for root in repo.list_all() if root.id in scan.root_ids]
    return [root for root in repo.list_all() if root.enabled]


def _prefetch(paths: Sequence[str], done: Semaphore, stop: Event) -> None:
    """Pull files into the OS page cache ahead of the pool.

    A worker reads a file and then decodes it, so its core idles while the disk
    works. Reading ahead on a separate thread keeps the disk busy, so by the time
    a worker opens a file the bytes are already cached. Nothing is passed between
    processes: the payload is the page cache, not a pickled buffer, which would
    cost more than the stall it removes.

    **The gain is real but modest, and smaller than it first appeared.** Three
    cold-cache A/B runs against an external USB drive came out at 1.08x, 1.11x
    and 1.40x — positive every time, never negative, but not resolvable more
    precisely than that: the drive's own throughput wandered between 20 and
    91 MB/s across blocks of the same run, which is a far bigger effect than the
    one being measured. An earlier reading of the import numbers suggested reads
    and decoding were fully serialised and that this would roughly halve import
    time. It does not: a cold baseline run reaches close to the decode-only rate
    on its own, so most of the overlap was already happening.

    Kept because the direction is consistent and the mechanism is sound, and
    because SCAN_PREFETCH=0 turns it off if it ever looks otherwise.

    `done` bounds how far ahead this runs — released once per completed photo.
    Without it, a big enough batch would evict the pages it just loaded before
    any worker got to them.
    """
    for path in paths:
        while not done.acquire(timeout=0.5):
            if stop.is_set():
                return
        if stop.is_set():
            return
        try:
            with open(path, "rb") as handle:
                while handle.read(1 << 20):
                    pass
        except OSError:
            # The pool reports read failures properly; this is only a warm-up.
            continue


@contextmanager
def _batch_processor(workers: int) -> Iterator[BatchProcessor]:
    """Serial when workers=0; otherwise a process pool for CPU-bound decode/hash."""
    settings = get_settings()
    worker_fn = partial(
        process_file,
        thumb_dir=str(settings.thumbnail_cache_dir),
        thumb_size=settings.thumbnail_size,
    )
    if workers == 0:
        yield lambda paths: [worker_fn(path) for path in paths]
        return
    max_workers = workers if workers > 0 else max(1, (os.cpu_count() or 2) - 1)
    lookahead = max(max_workers * 4, settings.scan_prefetch)

    def run(paths: Sequence[str]) -> list[ProcessedFile]:
        if not settings.scan_prefetch:
            return list(pool.map(worker_fn, paths, chunksize=8))
        done = Semaphore(lookahead)
        stop = Event()
        reader = Thread(target=_prefetch, args=(paths, done, stop), daemon=True)
        reader.start()
        try:
            results = []
            for result in pool.map(worker_fn, paths, chunksize=8):
                results.append(result)
                done.release()
            return results
        finally:
            stop.set()
            reader.join(timeout=2)

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        yield run


def _scan_root(
    session: Session,
    scans: ScanRepository,
    photos: PhotoRepository,
    scan: Scan,
    root: ScanRoot,
    run_batch: BatchProcessor,
    batch_size: int,
    added_by_sha: dict[str, list[str]],
    touched: TouchedPhotos,
) -> tuple[bool, dict[str, ExistingFile], set[str]]:
    """Walk one root. Returns (cancelled, existing index, paths seen on disk)."""
    existing = photos.index_for_root(root.id)
    seen: set[str] = set()
    pending: list[str] = []

    def flush() -> bool:
        if pending:
            for result in run_batch(pending):
                _apply_result(session, scans, scan, root, existing, result, added_by_sha, touched)
            scan.current_path = pending[-1]
            pending.clear()
        session.commit()
        return scans.current_status(scan.id) == "cancelled"

    for item in walk_root(Path(root.path)):
        if isinstance(item, DiscoveryError):
            scans.add_error(scan, item.path, item.error)
            continue
        scan.files_found += 1
        seen.add(item.path)
        if _is_unchanged(existing.get(item.path), item):
            scan.files_unchanged += 1
            scan.files_processed += 1
            continue
        pending.append(item.path)
        if len(pending) >= batch_size and flush():
            return True, existing, seen
    return flush(), existing, seen


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
    added_by_sha: dict[str, list[str]],
    touched: TouchedPhotos,
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
        "latitude": meta.latitude if meta else None,
        "longitude": meta.longitude if meta else None,
        # Geocoded here in the parent, never in a pool worker: the lookup tree
        # is ~100 MB and would be built once per worker.
        **_place_fields(meta.latitude if meta else None, meta.longitude if meta else None),
        "exif": meta.exif if meta else None,
        "phash": result.phash,
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
        touched.added_paths.add(result.path)
        if result.sha256 is not None:
            added_by_sha.setdefault(result.sha256, []).append(result.path)
    else:
        photo = session.get(Photo, known.photo_id)
        if photo is not None:
            for key, value in fields.items():
                setattr(photo, key, value)
        scan.files_changed += 1
        touched.ids.add(known.photo_id)
    scan.files_processed += 1


def _reconcile_moves_and_missing(
    session: Session,
    scan: Scan,
    per_root: list[tuple[dict[str, ExistingFile], set[str]]],
    added_by_sha: dict[str, list[str]],
    touched: TouchedPhotos,
) -> None:
    """Pair vanished paths with same-content additions (moves); flag the rest missing.

    Matching by sha256 can pair the "wrong" copy when identical files move
    around, but content-identical pairings are interchangeable by definition.
    """
    for existing, seen in per_root:
        for path, info in existing.items():
            if path in seen:
                continue
            new_path = _take_added_path(added_by_sha, info.sha256)
            if new_path is not None:
                _record_move(session, scan, info, new_path)
            elif info.status == "active":
                photo = session.get(Photo, info.photo_id)
                if photo is not None:
                    photo.status = "missing"
                scan.files_missing += 1
                # Leaving the active set can shrink or dissolve its groups.
                touched.ids.add(info.photo_id)
    session.commit()


def _take_added_path(added_by_sha: dict[str, list[str]], sha256: str | None) -> str | None:
    if sha256 is None:
        return None
    paths = added_by_sha.get(sha256)
    if not paths:
        return None
    return paths.pop()


def _record_move(session: Session, scan: Scan, info: ExistingFile, new_path: str) -> None:
    """Keep the original Photo row (stable id for decisions/audit); retarget its path."""
    new_photo = session.scalar(select(Photo).where(Photo.path == new_path))
    old_photo = session.get(Photo, info.photo_id)
    if new_photo is None or old_photo is None:  # pragma: no cover - defensive
        return
    copied = {
        column: getattr(new_photo, column)
        for column in (
            "path",
            "root_id",
            "filename",
            "ext",
            "mime",
            "size_bytes",
            "mtime_ns",
            "width",
            "height",
            "captured_at",
            "camera_make",
            "camera_model",
            "latitude",
            "longitude",
            "city",
            "region",
            "country",
            "place_distance_km",
            "exif",
            "sha256",
            "phash",
            "last_error",
        )
    }
    session.delete(new_photo)
    session.flush()  # release the unique(path) constraint before retargeting
    for column, value in copied.items():
        setattr(old_photo, column, value)
    old_photo.status = "active"
    scan.files_moved += 1
    scan.files_added -= 1


def recover_interrupted_scans(session: Session) -> int:
    """Mark scans left pending/running by a crash or restart as failed.

    Cheap to re-run: the next scan skips unchanged files, so nothing is lost
    beyond the final uncommitted batch.
    """
    stale = session.scalars(select(Scan).where(Scan.status.in_(ACTIVE_SCAN_STATUSES))).all()
    for scan in stale:
        scan.status = "failed"
        scan.message = (
            "Interrupted by an app restart. Re-run the scan; unchanged files are skipped."
        )
        scan.finished_at = datetime.now(UTC)
    session.commit()
    if stale:
        logger.warning("recovered %d interrupted scan(s)", len(stale))
    return len(stale)
