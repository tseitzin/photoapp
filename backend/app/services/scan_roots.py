from collections.abc import Sequence
from pathlib import Path

from app.models import ScanRoot
from app.repositories.scan_roots import ScanRootRepository
from app.services.errors import ConflictError, NotFoundError, ValidationFailedError


class ScanRootService:
    def __init__(self, repository: ScanRootRepository) -> None:
        self._repository = repository

    def list_roots(self) -> Sequence[ScanRoot]:
        return self._repository.list_all()

    def add_root(self, raw_path: str) -> ScanRoot:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ValidationFailedError("Scan root must be an absolute path")
        path = path.resolve()
        if not path.is_dir():
            raise ValidationFailedError(f"Scan root is not an existing directory: {path}")

        for existing in self._repository.list_all():
            existing_path = Path(existing.path)
            if path == existing_path:
                raise ConflictError(f"Scan root already configured: {path}")
            # Nested roots would index the same files twice.
            if path.is_relative_to(existing_path):
                raise ConflictError(f"{path} is inside the existing scan root {existing_path}")
            if existing_path.is_relative_to(path):
                raise ConflictError(f"{path} contains the existing scan root {existing_path}")

        return self._repository.add(str(path))

    def set_enabled(self, root_id: int, enabled: bool) -> ScanRoot:
        root = self._get(root_id)
        return self._repository.set_enabled(root, enabled)

    def remove_root(self, root_id: int) -> None:
        self._repository.delete(self._get(root_id))

    def _get(self, root_id: int) -> ScanRoot:
        root = self._repository.get(root_id)
        if root is None:
            raise NotFoundError(f"Scan root {root_id} not found")
        return root
