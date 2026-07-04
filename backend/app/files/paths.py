"""Path validation for every file-mutating operation.

All checks compare fully-resolved (symlink-free) paths, so neither `..`
segments nor symlinks planted inside a library can direct an operation
outside the approved directories.
"""

import os
from collections.abc import Iterable
from pathlib import Path


class PathValidationError(Exception):
    """The requested path fails a safety check; the operation must not run."""


def resolve_existing_file(raw: str) -> Path:
    """Resolve symlinks strictly; the target must exist and be a regular file."""
    try:
        resolved = Path(raw).resolve(strict=True)
    except OSError as exc:
        raise PathValidationError(f"Cannot resolve {raw}: {exc}") from exc
    if not resolved.is_file():
        raise PathValidationError(f"Not a regular file: {resolved}")
    return resolved


def resolve_lenient(raw: str) -> Path:
    """Resolve a path that may not exist yet (e.g. a restore destination)."""
    return Path(os.path.realpath(raw))


def ensure_within(path: Path, allowed: Iterable[Path], description: str) -> None:
    bases = [Path(os.path.realpath(base)) for base in allowed]
    if not any(path.is_relative_to(base) for base in bases):
        raise PathValidationError(f"{description} is outside approved directories: {path}")
