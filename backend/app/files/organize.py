"""Physical organize — move Library photos into a chosen folder structure.

Same safety rules as quarantine: every source and destination is validated
against approved scan roots on fully-resolved paths, destinations are never
overwritten (collisions get numeric suffixes), and every move is appended to
the file_operations audit log under one batch id.

`build_plan` is the only code that computes destinations; both the preview
endpoint and the execute job call it, so what the user approves is what runs.
Planning does no per-file disk access — it must stay sub-second at 50k photos.
The executor stats each destination right before its move instead.
"""

import logging
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.files.audit import record_operation
from app.files.paths import (
    PathValidationError,
    ensure_within,
    resolve_existing_file,
    resolve_lenient,
)
from app.models import Photo, ScanRoot
from app.repositories.duplicates import DuplicateRepository
from app.repositories.organize import OrganizeRunRepository
from app.repositories.photos import PhotoRepository
from app.services.errors import ValidationFailedError

logger = logging.getLogger(__name__)

MODES = ("keep", "date", "camera")
UNDATED_DIR = "Undated"
UNKNOWN_CAMERA_DIR = "Unknown camera"
_COMMIT_CHUNK = 200
_MAX_SEGMENT_LEN = 80

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class OrganizeSpec:
    folders: tuple[str, ...]
    destination: str
    mode: str
    rename: bool
    skip_duplicates: bool

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "OrganizeSpec":
        return cls(
            folders=tuple(params["folders"]),
            destination=params["destination"],
            mode=params["mode"],
            rename=bool(params.get("rename", False)),
            skip_duplicates=bool(params.get("skip_duplicates", True)),
        )

    def as_params(self) -> dict[str, Any]:
        return {
            "folders": list(self.folders),
            "destination": self.destination,
            "mode": self.mode,
            "rename": self.rename,
            "skip_duplicates": self.skip_duplicates,
        }


@dataclass(frozen=True)
class PlannedMove:
    photo_id: int
    src: str
    dest: str


@dataclass(frozen=True)
class OrganizePlan:
    spec: OrganizeSpec
    moves: list[PlannedMove]
    total: int
    duplicates_in_set: int
    duplicates_skipped: int
    already_organized: int
    undated: int
    est_bytes: int
    rename_example: tuple[str, str] | None
    # True when the destination lies outside every scan root today — starting
    # the run will register it so the moved photos stay in the Library.
    destination_new_root: bool


def validate_spec(session: Session, spec: OrganizeSpec) -> tuple[Path, list[Path]]:
    """Cheap up-front checks shared by preview and start. Returns
    (resolved destination, approved roots).

    The destination may lie outside the approved roots — starting a run
    registers it as a new scan root automatically (see
    services/organize.py::_ensure_destination_root), so organized photos stay
    indexed. Only the quarantine folder is off-limits."""
    if spec.mode not in MODES:
        raise ValidationFailedError(f"Unknown organize mode: {spec.mode}")
    if not spec.folders:
        raise ValidationFailedError("No folders selected")
    roots = [Path(root.path) for root in session.scalars(select(ScanRoot)).all()]
    if not roots:
        raise ValidationFailedError("No scan roots configured")
    destination = resolve_lenient(spec.destination)
    quarantine = resolve_lenient(str(get_settings().quarantine_dir))
    if destination.is_relative_to(quarantine):
        raise ValidationFailedError("Destination cannot be inside the quarantine folder")
    try:
        for folder in spec.folders:
            ensure_within(resolve_lenient(folder), roots, "Selected folder")
    except PathValidationError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return destination, roots


def build_plan(session: Session, spec: OrganizeSpec) -> OrganizePlan:
    destination, roots = validate_spec(session, spec)
    destination_new_root = not any(destination.is_relative_to(root) for root in roots)
    folders = _normalize_folders(spec.folders)
    photos = PhotoRepository(session).list_active_under(folders)
    duplicate_ids = DuplicateRepository(session).non_keeper_exact_member_ids(
        [photo.id for photo in photos]
    )
    # Any indexed path under the destination is occupied, whatever the photo's
    # status — photos.path is UNIQUE, and quarantined rows keep their old paths.
    taken = PhotoRepository(session).paths_under(str(destination))
    claimed: set[str] = set()

    moves: list[PlannedMove] = []
    duplicates_skipped = 0
    already_organized = 0
    undated = 0
    est_bytes = 0
    rename_example: tuple[str, str] | None = None

    for photo in photos:
        if spec.skip_duplicates and photo.id in duplicate_ids:
            duplicates_skipped += 1
            continue
        target_dir, is_undated = _target_dir(destination, folders, spec.mode, photo)
        if is_undated:
            undated += 1
        candidate = str(target_dir / _target_filename(spec, photo))
        if candidate == photo.path:
            already_organized += 1
            continue
        final = _next_free(candidate, claimed, taken)
        claimed.add(final)
        moves.append(PlannedMove(photo_id=photo.id, src=photo.path, dest=final))
        est_bytes += photo.size_bytes
        if rename_example is None and Path(final).name != photo.filename:
            rename_example = (photo.filename, Path(final).name)

    return OrganizePlan(
        spec=spec,
        moves=moves,
        total=len(photos),
        duplicates_in_set=len(duplicate_ids),
        duplicates_skipped=duplicates_skipped,
        already_organized=already_organized,
        undated=undated,
        est_bytes=est_bytes,
        rename_example=rename_example,
        destination_new_root=destination_new_root,
    )


def _normalize_folders(folders: Sequence[str]) -> list[str]:
    """Drop trailing slashes and folders nested inside other selected folders."""
    cleaned = sorted({folder.rstrip("/") for folder in folders if folder.rstrip("/")})
    kept: list[str] = []
    for folder in cleaned:  # lexicographic order puts parents before children
        if not any(folder.startswith(f"{outer}/") for outer in kept):
            kept.append(folder)
    return kept


def _target_dir(
    destination: Path, folders: list[str], mode: str, photo: Photo
) -> tuple[Path, bool]:
    """Directory the photo belongs in; the flag marks the Undated fallback."""
    if mode == "date":
        if photo.captured_at is None:
            return destination / UNDATED_DIR, True
        return destination / f"{photo.captured_at:%Y}" / f"{photo.captured_at:%m}", False
    if mode == "camera":
        return destination / _sanitize_segment(photo.camera_model), False
    # keep: the selected folder's name plus the photo's subpath beneath it.
    selected = next(f for f in folders if photo.path.startswith(f"{f}/"))
    relative = Path(photo.path).parent.relative_to(selected)
    return destination / Path(selected).name / relative, False


def _sanitize_segment(name: str | None) -> str:
    if name is None:
        return UNKNOWN_CAMERA_DIR
    cleaned = name.replace("/", "-").replace("\x00", "").strip().lstrip(".")
    return cleaned[:_MAX_SEGMENT_LEN].strip() or UNKNOWN_CAMERA_DIR


def _target_filename(spec: OrganizeSpec, photo: Photo) -> str:
    # Undated photos keep their name: a rename pattern needs a capture time.
    if spec.rename and photo.captured_at is not None:
        return f"{photo.captured_at:%Y-%m-%d_%H%M%S}{Path(photo.path).suffix.lower()}"
    return photo.filename


def _suffixed(candidate: str, counter: int) -> str:
    path = Path(candidate)
    return str(path.parent / f"{path.stem}_{counter:02d}{path.suffix}")


def _next_free(candidate: str, claimed: set[str], taken: set[str]) -> str:
    final = candidate
    counter = 0
    while final in claimed or final in taken:
        counter += 1
        final = _suffixed(candidate, counter)
    return final


def execute_organize(run_id: int, session_factory: SessionFactory) -> None:
    """Background job body. Opens its own session; safe to run in any runner."""
    with session_factory() as session:
        runs = OrganizeRunRepository(session)
        run = runs.get(run_id)
        if run is None:  # pragma: no cover - job outliving its row is a bug
            logger.error("organize run %s vanished before execution", run_id)
            return
        runs.mark_running(run)
        try:
            spec = OrganizeSpec.from_params(run.params)
            plan = build_plan(session, spec)
            run.total = plan.total
            run.planned = len(plan.moves)
            run.skipped_duplicates = plan.duplicates_skipped
            run.already_organized = plan.already_organized
            run.undated = plan.undated
            run.est_bytes = plan.est_bytes
            runs.commit()  # first poll already shows the totals

            root_rows = session.scalars(select(ScanRoot)).all()
            roots = [Path(root.path) for root in root_rows]
            # Paths any planned move will occupy or that the DB already holds:
            # the executor's re-suffixing must not step on them either.
            reserved = {move.dest for move in plan.moves} | PhotoRepository(session).paths_under(
                spec.destination
            )
            last_error: str | None = None

            for index, move in enumerate(plan.moves, start=1):
                photo = session.get(Photo, move.photo_id)
                if photo is None or photo.status != "active" or photo.path != move.src:
                    run.failed_count += 1
                    last_error = f"{move.src}: photo changed since planning"
                    continue
                try:
                    source = resolve_existing_file(move.src)
                    ensure_within(source, roots, "Photo file")
                    dest = resolve_lenient(move.dest)
                    ensure_within(dest, roots, "Organize destination")
                    dest = _next_free_on_disk(dest, reserved)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(dest))
                except (PathValidationError, OSError) as exc:
                    run.failed_count += 1
                    last_error = str(exc)
                    continue
                reserved.add(str(dest))
                photo.path = str(dest)
                photo.filename = dest.name
                photo.root_id = _root_id_for(root_rows, dest) or photo.root_id
                record_operation(
                    session,
                    photo.id,
                    "organize",
                    move.src,
                    str(dest),
                    run.batch_id,
                    photo.size_bytes,
                )
                run.moved += 1
                if index % _COMMIT_CHUNK == 0:
                    runs.commit()

            runs.mark_finished(run, "completed", message=last_error)
            logger.info(
                "organize run %s completed: %s moved, %s failed",
                run_id,
                run.moved,
                run.failed_count,
            )
        except Exception as exc:
            logger.exception("organize run %s failed", run_id)
            session.rollback()
            runs.mark_finished(run, "failed", message=f"{type(exc).__name__}: {exc}")


def _next_free_on_disk(dest: Path, reserved: set[str]) -> Path:
    """Planning avoided DB collisions without touching the disk; the one stat
    that matters happens here, immediately before the move."""
    if not dest.exists():
        return dest
    counter = 0
    while True:
        counter += 1
        candidate = Path(_suffixed(str(dest), counter))
        if str(candidate) not in reserved and not candidate.exists():
            return candidate


def _root_id_for(roots: Sequence[ScanRoot], path: Path) -> int | None:
    """Root containing the path — longest prefix wins (roots never nest, but
    stay deterministic regardless)."""
    best: ScanRoot | None = None
    for root in roots:
        if path.is_relative_to(root.path) and (best is None or len(root.path) > len(best.path)):
            best = root
    return best.id if best else None
