from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanRoot


class ScanRootRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> Sequence[ScanRoot]:
        return self._session.scalars(select(ScanRoot).order_by(ScanRoot.path)).all()

    def get(self, root_id: int) -> ScanRoot | None:
        return self._session.get(ScanRoot, root_id)

    def get_by_path(self, path: str) -> ScanRoot | None:
        return self._session.scalar(select(ScanRoot).where(ScanRoot.path == path))

    def add(self, path: str) -> ScanRoot:
        root = ScanRoot(path=path)
        self._session.add(root)
        self._session.commit()
        self._session.refresh(root)
        return root

    def set_enabled(self, root: ScanRoot, enabled: bool) -> ScanRoot:
        root.enabled = enabled
        self._session.commit()
        self._session.refresh(root)
        return root

    def delete(self, root: ScanRoot) -> None:
        self._session.delete(root)
        self._session.commit()
