"""Generated test images — tests must never touch a real photo library."""

from pathlib import Path

from PIL import Image


def make_image(
    path: Path,
    size: tuple[int, int] = (64, 48),
    color: str = "steelblue",
    exif_fields: dict[int, str] | None = None,
    exif_ifd_fields: dict[int, str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color)
    if exif_fields or exif_ifd_fields:
        exif = Image.Exif()
        for tag, value in (exif_fields or {}).items():
            exif[tag] = value
        if exif_ifd_fields:
            ifd = exif.get_ifd(0x8769)
            for tag, value in exif_ifd_fields.items():
                ifd[tag] = value
        image.save(path, exif=exif)
    else:
        image.save(path)
    return path


def make_textured_image(
    path: Path, seed: int, size: tuple[int, int] = (400, 300), quality: int = 92
) -> Path:
    """Deterministic low-frequency random blocks, distinct per seed.

    Flat or periodic images have degenerate/near-identical pHashes; seeded
    random block luminance gives each seed an essentially random hash while
    staying stable under resize/recompress (what pHash is supposed to match).
    """
    import random

    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    cols, rows = 16, 12
    blocks = Image.new("RGB", (cols, rows))
    blocks.putdata(
        [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(cols * rows)]
    )
    image = blocks.resize(size, Image.Resampling.BILINEAR)
    image.save(path, quality=quality)
    return path
