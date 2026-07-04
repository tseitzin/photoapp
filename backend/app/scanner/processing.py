"""Per-file processing: one read of the bytes feeds both SHA-256 and decode.

Module-level function + primitive dataclasses so ProcessPoolExecutor can
pickle work across processes.
"""

import hashlib
import os
from dataclasses import dataclass

from app.scanner.metadata import ImageMetadata, extract_metadata


@dataclass(frozen=True)
class ProcessedFile:
    path: str
    size_bytes: int
    mtime_ns: int
    sha256: str | None
    metadata: ImageMetadata | None
    error: str | None

    @property
    def readable(self) -> bool:
        return self.sha256 is not None


def process_file(path: str) -> ProcessedFile:
    try:
        stat = os.stat(path)
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return ProcessedFile(
            path=path, size_bytes=0, mtime_ns=0, sha256=None, metadata=None, error=str(exc)
        )

    sha256 = hashlib.sha256(data).hexdigest()
    try:
        metadata: ImageMetadata | None = extract_metadata(data)
        error = None
    except Exception as exc:  # noqa: BLE001 - corrupt files are data, not bugs
        metadata = None
        error = f"{type(exc).__name__}: {exc}"

    return ProcessedFile(
        path=path,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=sha256,
        metadata=metadata,
        error=error,
    )
