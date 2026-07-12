from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.orm import Session

from app.models import DuplicateDecision, Photo

# Facet/filter canonicalization: one chip covers equivalent extensions.
CANONICAL_EXT = {"jpg": "jpeg", "tif": "tiff", "heif": "heic"}
_EXPAND_EXT: dict[str, list[str]] = {
    "jpeg": ["jpg", "jpeg"],
    "tiff": ["tif", "tiff"],
    "heic": ["heic", "heif"],
}


def expand_ext_filter(values: Sequence[str]) -> list[str]:
    expanded: list[str] = []
    for value in values:
        expanded.extend(_EXPAND_EXT.get(value.lower(), [value.lower()]))
    return expanded


_SORTS: dict[str, tuple[ColumnElement[Any], ...]] = {
    "captured_desc": (Photo.captured_at.desc().nulls_last(), Photo.id.desc()),
    "captured_asc": (Photo.captured_at.asc().nulls_last(), Photo.id.asc()),
    "name_asc": (Photo.filename.asc(), Photo.id.asc()),
    "name_desc": (Photo.filename.desc(), Photo.id.desc()),
    "size_desc": (Photo.size_bytes.desc(), Photo.id.desc()),
    "size_asc": (Photo.size_bytes.asc(), Photo.id.asc()),
    # Most recently indexed first — "Recent imports" on Home.
    "added_desc": (Photo.id.desc(),),
}


class ExistingFile:
    """Slim in-memory view of an indexed file, used for change/move detection."""

    __slots__ = ("photo_id", "size_bytes", "mtime_ns", "status", "sha256")

    def __init__(
        self,
        photo_id: int,
        size_bytes: int,
        mtime_ns: int,
        status: str,
        sha256: str | None,
    ) -> None:
        self.photo_id = photo_id
        self.size_bytes = size_bytes
        self.mtime_ns = mtime_ns
        self.status = status
        self.sha256 = sha256


class PhotoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def index_for_root(self, root_id: int) -> dict[str, ExistingFile]:
        """path -> ExistingFile for every photo under a root.

        ~150 bytes per entry; even a 500k-photo root stays well under 100 MB,
        and it turns per-file change detection into a dict lookup.
        """
        rows = self._session.execute(
            select(
                Photo.path,
                Photo.id,
                Photo.size_bytes,
                Photo.mtime_ns,
                Photo.status,
                Photo.sha256,
            ).where(Photo.root_id == root_id)
        )
        return {
            path: ExistingFile(photo_id, size, mtime, status, sha256)
            for path, photo_id, size, mtime, status, sha256 in rows
        }

    def get(self, photo_id: int) -> Photo | None:
        return self._session.get(Photo, photo_id)

    def get_by_path(self, path: str) -> Photo | None:
        return self._session.scalar(select(Photo).where(Photo.path == path))

    def set_marked(self, photo_ids: Sequence[int], marked: bool) -> int:
        """Flag/unflag active photos for deletion. Returns active rows affected."""
        if not photo_ids:
            return 0
        target = (Photo.id.in_(photo_ids), Photo.status == "active")
        affected = self._session.scalar(select(func.count()).select_from(Photo).where(*target)) or 0
        self._session.execute(update(Photo).where(*target).values(marked_for_deletion=marked))
        self._session.commit()
        return affected

    def list_marked_for_removal(self) -> Sequence[Photo]:
        """Active photos flagged from the Library or via a duplicate 'remove'."""
        has_remove_decision = (
            select(DuplicateDecision.photo_id)
            .where(DuplicateDecision.decision == "remove")
            .scalar_subquery()
        )
        return self._session.scalars(
            select(Photo)
            .where(
                Photo.status == "active",
                or_(Photo.marked_for_deletion.is_(True), Photo.id.in_(has_remove_decision)),
            )
            .order_by(Photo.path)
        ).all()

    def list_active_under(self, folders: Sequence[str]) -> Sequence[Photo]:
        """Active photos under any of the given folders, in stable path order."""
        if not folders:
            return []
        return self._session.scalars(
            select(Photo)
            .where(
                Photo.status == "active",
                or_(*[Photo.path.like(f"{folder.rstrip('/')}/%") for folder in folders]),
            )
            .order_by(Photo.path)
        ).all()

    def paths_under(self, prefix: str) -> set[str]:
        """Every indexed path under a directory, regardless of photo status.

        Quarantined/missing rows keep their old paths and photos.path is UNIQUE,
        so destination planning must treat those paths as occupied too.
        """
        normalized = prefix.rstrip("/")
        return set(
            self._session.scalars(select(Photo.path).where(Photo.path.like(f"{normalized}/%")))
        )

    def list_page(
        self,
        limit: int,
        offset: int,
        status: str | None = None,
        folder: str | None = None,
        exts: Sequence[str] | None = None,
        cameras: Sequence[str] | None = None,
        q: str | None = None,
        sort: str = "captured_desc",
    ) -> tuple[Sequence[Photo], int]:
        conditions = []
        if status is not None:
            conditions.append(Photo.status == status)
        if folder is not None:
            normalized = folder.rstrip("/")
            conditions.append(
                Photo.path.like(f"{normalized}/%")
                if normalized
                else Photo.path.like("/%")  # degenerate input: match everything
            )
        if exts:
            conditions.append(Photo.ext.in_([e.lower() for e in exts]))
        if cameras:
            conditions.append(Photo.camera_model.in_(list(cameras)))
        if q:
            conditions.append(Photo.filename.ilike(f"%{q}%"))

        query = select(Photo).where(*conditions)
        total = (
            self._session.scalar(select(func.count()).select_from(Photo).where(*conditions)) or 0
        )
        items = self._session.scalars(
            query.order_by(*_SORTS.get(sort, _SORTS["captured_desc"])).limit(limit).offset(offset)
        ).all()
        return items, total

    def similar_to(self, photo: Photo, threshold: int, limit: int) -> list[tuple[Photo, int]]:
        """LSH candidate lookup in SQL: indexed band equality narrows the field,
        bit_count verifies the exact Hamming distance. Complete for threshold <= 7."""
        if photo.phash is None:
            return []
        band_conditions = [
            getattr(Photo, f"phash_b{band}") == ((photo.phash >> (band * 8)) & 255)
            for band in range(8)
        ]
        # bit_count() takes bit/bytea, not bigint — cast the XOR result.
        distance = func.bit_count(cast(Photo.phash.op("#")(photo.phash), BIT(64)))
        rows = self._session.execute(
            select(Photo, distance)
            .where(
                Photo.id != photo.id,
                Photo.status == "active",
                Photo.phash.is_not(None),
                or_(*band_conditions),
                distance <= threshold,
            )
            .order_by(distance, Photo.id)
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in rows]

    def facets(self) -> tuple[dict[str, int], dict[str, int]]:
        """(file-type counts, camera counts) over non-quarantined photos.

        jpg/jpeg and tif/tiff are merged into one canonical facet each.
        """
        visible = Photo.status != "quarantined"
        type_counts: dict[str, int] = {}
        for ext, count in self._session.execute(
            select(Photo.ext, func.count()).where(visible).group_by(Photo.ext)
        ):
            type_counts[CANONICAL_EXT.get(ext, ext)] = (
                type_counts.get(CANONICAL_EXT.get(ext, ext), 0) + count
            )
        camera_counts = {
            camera: count
            for camera, count in self._session.execute(
                select(Photo.camera_model, func.count())
                .where(visible, Photo.camera_model.is_not(None))
                .group_by(Photo.camera_model)
                .order_by(func.count().desc())
            )
        }
        return type_counts, camera_counts
