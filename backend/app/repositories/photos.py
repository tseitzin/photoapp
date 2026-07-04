from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Photo


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

    def list_page(
        self, limit: int, offset: int, status: str | None = None
    ) -> tuple[Sequence[Photo], int]:
        query = select(Photo)
        count_query = select(func.count()).select_from(Photo)
        if status is not None:
            query = query.where(Photo.status == status)
            count_query = count_query.where(Photo.status == status)
        total = self._session.scalar(count_query) or 0
        items = self._session.scalars(
            query.order_by(Photo.captured_at.desc().nulls_last(), Photo.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return items, total
