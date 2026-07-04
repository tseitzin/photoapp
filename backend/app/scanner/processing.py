"""Per-file processing: one read of the bytes feeds SHA-256, metadata,
perceptual hash, and the grid thumbnail.

Module-level function + primitive dataclasses so ProcessPoolExecutor can
pickle work across processes.
"""

import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path

import imagehash
from PIL import Image, ImageOps

from app.scanner.metadata import ImageMetadata, read_metadata
from app.scanner.thumbnails import write_thumbnail


@dataclass(frozen=True)
class ProcessedFile:
    path: str
    size_bytes: int
    mtime_ns: int
    sha256: str | None
    metadata: ImageMetadata | None
    phash: int | None
    error: str | None

    @property
    def readable(self) -> bool:
        return self.sha256 is not None


def _phash64(image: Image.Image) -> int:
    """64-bit pHash as a signed integer (fits Postgres BIGINT)."""
    value = int(str(imagehash.phash(image)), 16)
    return value - (1 << 64) if value >= (1 << 63) else value


def process_file(path: str, thumb_dir: str | None = None, thumb_size: int = 512) -> ProcessedFile:
    try:
        stat = os.stat(path)
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return ProcessedFile(
            path=path,
            size_bytes=0,
            mtime_ns=0,
            sha256=None,
            metadata=None,
            phash=None,
            error=str(exc),
        )

    sha256 = hashlib.sha256(data).hexdigest()
    metadata: ImageMetadata | None = None
    phash: int | None = None
    error: str | None = None
    try:
        with Image.open(io.BytesIO(data)) as image:
            oriented = ImageOps.exif_transpose(image)
            metadata = read_metadata(image, oriented.width, oriented.height)
            phash = _phash64(oriented)
            if thumb_dir is not None:
                write_thumbnail(oriented, Path(thumb_dir), sha256, thumb_size)
    except Exception as exc:  # noqa: BLE001 - corrupt files are data, not bugs
        error = f"{type(exc).__name__}: {exc}"

    return ProcessedFile(
        path=path,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=sha256,
        metadata=metadata,
        phash=phash,
        error=error,
    )
