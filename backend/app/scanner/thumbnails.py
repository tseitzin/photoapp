"""Content-addressed thumbnail cache.

Keys are the file's sha256, so identical files share one thumbnail and any
content change produces a new key automatically (stale entries are just
unreferenced files). The whole cache can be deleted and rebuilt on demand.
"""

import io
import logging
import os
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

_WEBP_QUALITY = 80


def thumbnail_path(cache_dir: Path, sha256: str, size: int) -> Path:
    return cache_dir / str(size) / sha256[:2] / f"{sha256}.webp"


def write_thumbnail(image: Image.Image, cache_dir: Path, sha256: str, size: int) -> Path:
    """Write a ``size``-bounded webp for an already-decoded (oriented) image."""
    target = thumbnail_path(cache_dir, sha256, size)
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    thumb = image.copy()
    thumb.thumbnail((size, size))
    if thumb.mode not in ("RGB", "RGBA"):
        thumb = thumb.convert("RGB")
    # Unique per call (not just per process): two threads generating the same
    # sha256 (e.g. both panes of an exact-duplicate compare) must not share a
    # temp file, or their writes corrupt each other. Both then os.replace onto
    # the same target atomically — identical content, so last writer wins safely.
    tmp = target.with_name(f"{target.name}.{uuid4().hex}.tmp")
    try:
        thumb.save(tmp, "WEBP", quality=_WEBP_QUALITY)
        os.replace(tmp, target)  # atomic: readers never see a partial file
    finally:
        tmp.unlink(missing_ok=True)  # clean up if save/replace failed partway
    return target


def ensure_thumbnail(source_path: str, sha256: str, cache_dir: Path, size: int) -> Path | None:
    """Return the cached thumbnail, generating it from the original if needed."""
    target = thumbnail_path(cache_dir, sha256, size)
    if target.exists():
        return target
    try:
        with open(source_path, "rb") as fh:
            data = fh.read()
        with Image.open(io.BytesIO(data)) as image:
            oriented = ImageOps.exif_transpose(image)
            return write_thumbnail(oriented, cache_dir, sha256, size)
    except Exception:  # noqa: BLE001 - a broken original must not 500 the API
        logger.warning("could not generate thumbnail for %s", source_path, exc_info=True)
        return None
