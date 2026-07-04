"""Streaming discovery of supported image files under a scan root.

Design constraints (see docs/ARCHITECTURE.md):
- never follow symlinks (no cycles, no escaping the approved root),
- one failure never aborts the walk — errors are yielded alongside results,
- generator-based so 100k+ files are never held in memory at once.
"""

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# RAW formats deliberately excluded in v1 (no decoder); HEIC/HEIF via pillow-heif.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tif", ".tiff"}
)


@dataclass(frozen=True)
class DiscoveredFile:
    path: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class DiscoveryError:
    path: str
    error: str


def walk_root(root: Path) -> Iterator[DiscoveredFile | DiscoveryError]:
    """Yield every supported image file under ``root``, plus any per-entry errors.

    Symlinks (files and directories) and hidden entries (dot-prefixed, e.g.
    .Trash, .photoslibrary internals the user hid) are skipped. Directories are
    additionally de-duplicated by (st_dev, st_ino) as a belt-and-braces guard
    against bind mounts / hardlinked dirs producing infinite or duplicate walks.
    """
    visited_dirs: set[tuple[int, int]] = set()
    pending: list[str] = [str(root)]

    while pending:
        current = pending.pop()
        try:
            stat = os.stat(current)
        except OSError as exc:
            yield DiscoveryError(path=current, error=str(exc))
            continue
        dir_key = (stat.st_dev, stat.st_ino)
        if dir_key in visited_dirs:
            continue
        visited_dirs.add(dir_key)

        try:
            entries = sorted(os.scandir(current), key=lambda e: e.name)
        except OSError as exc:
            yield DiscoveryError(path=current, error=str(exc))
            continue

        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                if Path(entry.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                yield DiscoveryError(path=entry.path, error=str(exc))
                continue
            yield DiscoveredFile(
                path=entry.path,
                size_bytes=entry_stat.st_size,
                mtime_ns=entry_stat.st_mtime_ns,
            )
