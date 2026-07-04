"""Derive duplicate groups from indexed photos (pure logic, no DB access).

Exact groups: photos sharing a sha256.
Similar groups arrive in the next milestone (LSH-banded pHash comparison).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PhotoInfo:
    """The slice of a photo the dedupe pass needs."""

    id: int
    sha256: str | None
    phash: int | None
    size_bytes: int
    width: int | None
    height: int | None


@dataclass(frozen=True)
class DerivedGroup:
    kind: str  # "exact" | "similar"
    key: str
    keeper_photo_id: int
    # photo_id -> similarity_pct (100 = byte-identical)
    members: dict[int, int]


def keeper_of(photos: list[PhotoInfo]) -> PhotoInfo:
    """Suggested keeper: highest resolution, then largest file, then oldest row."""
    return max(
        photos,
        key=lambda p: ((p.width or 0) * (p.height or 0), p.size_bytes, -p.id),
    )


def derive_exact_groups(photos: list[PhotoInfo]) -> list[DerivedGroup]:
    by_sha: dict[str, list[PhotoInfo]] = {}
    for photo in photos:
        if photo.sha256 is not None:
            by_sha.setdefault(photo.sha256, []).append(photo)

    groups: list[DerivedGroup] = []
    for sha256, copies in by_sha.items():
        if len(copies) < 2:
            continue
        groups.append(
            DerivedGroup(
                kind="exact",
                key=sha256,
                keeper_photo_id=keeper_of(copies).id,
                members={photo.id: 100 for photo in copies},
            )
        )
    return groups
