"""Quarantine-first file management — the only code that moves user files.

Rules (see docs/ARCHITECTURE.md):
- nothing is deleted directly: "removal" moves the file under QUARANTINE_DIR,
  mirroring its absolute source path, so every file has a unique, reversible slot;
- every move is validated against approved roots / the quarantine dir on
  fully-resolved paths, and appended to the file_operations audit log;
- destinations are never overwritten;
- a batch that would quarantine every remaining active member of a duplicate
  group is refused unless the caller explicitly forces it.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.files.paths import (
    PathValidationError,
    ensure_within,
    resolve_existing_file,
    resolve_lenient,
)
from app.models import DuplicateGroup, FileOperation, Photo, ScanRoot
from app.services.errors import ConflictError, ValidationFailedError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItemResult:
    photo_id: int
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class BatchResult:
    batch_id: str
    results: list[ItemResult]

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.ok)


class FileManagementService:
    def __init__(self, session: Session, quarantine_dir: Path | None = None) -> None:
        self._session = session
        self._quarantine_dir = resolve_lenient(str(quarantine_dir or get_settings().quarantine_dir))

    # -- helpers ------------------------------------------------------------

    def _approved_roots(self) -> list[Path]:
        return [Path(root.path) for root in self._session.scalars(select(ScanRoot)).all()]

    def _load_photos(self, photo_ids: list[int]) -> dict[int, Photo]:
        photos = self._session.scalars(select(Photo).where(Photo.id.in_(photo_ids))).all()
        return {photo.id: photo for photo in photos}

    def _audit(
        self,
        photo_id: int,
        op: str,
        src: str,
        dest: str | None,
        batch_id: str,
        size_bytes: int,
    ) -> None:
        self._session.add(
            FileOperation(
                photo_id=photo_id,
                op=op,
                src_path=src,
                dest_path=dest,
                batch_id=batch_id,
                size_bytes=size_bytes,
            )
        )

    def _quarantine_slot(self, source: Path) -> Path:
        # Mirror the absolute path under the quarantine dir: unique + reversible.
        return self._quarantine_dir / source.relative_to(source.anchor)

    def _latest_quarantine_op(self, photo_id: int) -> FileOperation | None:
        return self._session.scalar(
            select(FileOperation)
            .where(FileOperation.photo_id == photo_id, FileOperation.op == "quarantine")
            .order_by(FileOperation.id.desc())
            .limit(1)
        )

    def _groups_fully_covered(self, photo_ids: set[int]) -> list[int]:
        """Ids of duplicate groups whose every remaining active member is targeted."""
        covered: list[int] = []
        groups = self._session.scalars(select(DuplicateGroup)).unique().all()
        for group in groups:
            active_ids = {
                member.photo_id for member in group.members if member.photo.status == "active"
            }
            if active_ids and active_ids <= photo_ids:
                covered.append(group.id)
        return covered

    def _rebuild_groups(self) -> None:
        # Local import to avoid a service<->service import cycle at module load.
        from app.services.duplicates import rebuild_duplicate_groups

        rebuild_duplicate_groups(self._session)

    # -- operations ----------------------------------------------------------

    def quarantine(self, photo_ids: list[int], force: bool = False) -> BatchResult:
        if not photo_ids:
            raise ValidationFailedError("No photos given")
        if not force:
            covered = self._groups_fully_covered(set(photo_ids))
            if covered:
                raise ConflictError(
                    "This would remove every remaining photo in "
                    f"{len(covered)} duplicate group(s) (ids {covered}). "
                    "Pass force=true to do it anyway."
                )

        roots = self._approved_roots()
        photos = self._load_photos(photo_ids)
        batch_id = str(uuid4())
        results: list[ItemResult] = []
        for photo_id in photo_ids:
            photo = photos.get(photo_id)
            if photo is None:
                results.append(ItemResult(photo_id, ok=False, error="Photo not found"))
                continue
            if photo.status != "active":
                results.append(
                    ItemResult(photo_id, ok=False, error=f"Photo is {photo.status}, not active")
                )
                continue
            try:
                source = resolve_existing_file(photo.path)
                ensure_within(source, roots, "Photo file")
                dest = self._quarantine_slot(source)
                if dest.exists():
                    raise PathValidationError(f"Quarantine slot already occupied: {dest}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(dest))
            except (PathValidationError, OSError) as exc:
                results.append(ItemResult(photo_id, ok=False, error=str(exc)))
                continue
            photo.status = "quarantined"
            self._audit(photo_id, "quarantine", str(source), str(dest), batch_id, photo.size_bytes)
            results.append(ItemResult(photo_id, ok=True))
            logger.info("quarantined %s -> %s", source, dest)

        self._session.commit()
        if any(r.ok for r in results):
            self._rebuild_groups()
        return BatchResult(batch_id=batch_id, results=results)

    def restore(self, photo_ids: list[int]) -> BatchResult:
        if not photo_ids:
            raise ValidationFailedError("No photos given")
        roots = self._approved_roots()
        photos = self._load_photos(photo_ids)
        batch_id = str(uuid4())
        results: list[ItemResult] = []
        for photo_id in photo_ids:
            photo = photos.get(photo_id)
            if photo is None:
                results.append(ItemResult(photo_id, ok=False, error="Photo not found"))
                continue
            if photo.status != "quarantined":
                results.append(ItemResult(photo_id, ok=False, error="Photo is not quarantined"))
                continue
            op = self._latest_quarantine_op(photo_id)
            if op is None or op.dest_path is None:
                results.append(ItemResult(photo_id, ok=False, error="No quarantine record found"))
                continue
            try:
                source = resolve_existing_file(op.dest_path)
                ensure_within(source, [self._quarantine_dir], "Quarantined file")
                dest = resolve_lenient(photo.path)
                ensure_within(dest, roots, "Restore destination")
                if dest.exists():
                    raise PathValidationError(f"A file already exists at {dest}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(dest))
            except (PathValidationError, OSError) as exc:
                results.append(ItemResult(photo_id, ok=False, error=str(exc)))
                continue
            photo.status = "active"
            self._audit(photo_id, "restore", str(source), str(dest), batch_id, photo.size_bytes)
            results.append(ItemResult(photo_id, ok=True))
            logger.info("restored %s -> %s", source, dest)

        self._session.commit()
        if any(r.ok for r in results):
            self._rebuild_groups()
        return BatchResult(batch_id=batch_id, results=results)

    def delete_permanently(self, photo_ids: list[int], confirm: bool) -> BatchResult:
        """Delete quarantined files from disk. Refuses anything not quarantined."""
        if not confirm:
            raise ValidationFailedError(
                "Permanent deletion requires confirm=true — this cannot be undone"
            )
        if not photo_ids:
            raise ValidationFailedError("No photos given")
        photos = self._load_photos(photo_ids)
        batch_id = str(uuid4())
        results: list[ItemResult] = []
        for photo_id in photo_ids:
            photo = photos.get(photo_id)
            if photo is None:
                results.append(ItemResult(photo_id, ok=False, error="Photo not found"))
                continue
            if photo.status != "quarantined":
                results.append(
                    ItemResult(
                        photo_id,
                        ok=False,
                        error="Only quarantined photos can be permanently deleted",
                    )
                )
                continue
            op = self._latest_quarantine_op(photo_id)
            if op is None or op.dest_path is None:
                results.append(ItemResult(photo_id, ok=False, error="No quarantine record found"))
                continue
            try:
                target = resolve_existing_file(op.dest_path)
                ensure_within(target, [self._quarantine_dir], "File to delete")
                target.unlink()
            except (PathValidationError, OSError) as exc:
                results.append(ItemResult(photo_id, ok=False, error=str(exc)))
                continue
            self._audit(photo_id, "delete", str(target), None, batch_id, photo.size_bytes)
            # The file no longer exists anywhere; drop the index row. The audit
            # row keeps the path and size (photo_id becomes NULL via FK), so the
            # lifetime "space reclaimed" tally survives.
            self._session.delete(photo)
            results.append(ItemResult(photo_id, ok=True))
            logger.warning("permanently deleted %s", target)

        self._session.commit()
        return BatchResult(batch_id=batch_id, results=results)

    def reset_deletion_history(self) -> int:
        """Clear audit rows for files no longer in the library, starting the
        lifetime deletion tally fresh.

        Targets rows whose photo is gone (photo_id IS NULL) — that's every
        permanent-delete record plus the stale quarantine records left behind by
        deleted photos. Rows for photos that still exist (e.g. currently
        quarantined) are kept, so restore is unaffected. Returns rows cleared.
        """
        orphaned = FileOperation.photo_id.is_(None)
        cleared = (
            self._session.scalar(select(func.count()).select_from(FileOperation).where(orphaned))
            or 0
        )
        self._session.execute(delete(FileOperation).where(orphaned))
        self._session.commit()
        logger.info("reset deletion history: cleared %d audit row(s)", cleared)
        return cleared
