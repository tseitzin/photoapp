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
