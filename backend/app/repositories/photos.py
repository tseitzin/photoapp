from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Photo


class ExistingFile:
    """Slim in-memory view of an indexed file, used for change detection."""

    __slots__ = ("photo_id", "size_bytes", "mtime_ns", "status")

    def __init__(self, photo_id: int, size_bytes: int, mtime_ns: int, status: str) -> None:
        self.photo_id = photo_id
        self.size_bytes = size_bytes
        self.mtime_ns = mtime_ns
        self.status = status


class PhotoRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def index_for_root(self, root_id: int) -> dict[str, ExistingFile]:
        """path -> ExistingFile for every photo under a root.

        ~100 bytes per entry; even a 500k-photo root stays well under 100 MB,
        and it turns per-file change detection into a dict lookup.
        """
        rows = self._session.execute(
            select(Photo.path, Photo.id, Photo.size_bytes, Photo.mtime_ns, Photo.status).where(
                Photo.root_id == root_id
            )
        )
        return {
            path: ExistingFile(photo_id, size, mtime, status)
            for path, photo_id, size, mtime, status in rows
        }

    def get(self, photo_id: int) -> Photo | None:
        return self._session.get(Photo, photo_id)

    def get_by_ids(self, ids: Sequence[int]) -> Sequence[Photo]:
        return self._session.scalars(select(Photo).where(Photo.id.in_(ids))).all()

    def add(self, photo: Photo) -> None:
        self._session.add(photo)
