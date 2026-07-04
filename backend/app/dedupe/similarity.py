"""Near-duplicate detection over 64-bit perceptual hashes.

Candidate selection is LSH banding: hashes are split into 8 byte-bands and
only hashes sharing at least one band are compared. That is complete for any
Hamming threshold <= 7 (pigeonhole) and near-linear in practice. Identical
hashes are collapsed first, so pathological clusters (burst shots, flat
images) cost one representative each, not O(k^2).

pHash finds resized/recompressed/re-encoded variants; it does NOT find crops
or edits — that is the future embeddings path. Results are therefore always
labeled "visually similar", never "duplicates".
"""

from app.dedupe.grouping import DerivedGroup, PhotoInfo, keeper_of

BANDS = 8
BAND_BITS = 8
HASH_BITS = 64
_UNSIGNED_MASK = (1 << HASH_BITS) - 1


def to_unsigned(phash: int) -> int:
    return phash & _UNSIGNED_MASK


def hamming(a: int, b: int) -> int:
    """Hamming distance between two hashes (signed or unsigned)."""
    return (to_unsigned(a) ^ to_unsigned(b)).bit_count()


def band_values(unsigned_hash: int) -> tuple[int, ...]:
    return tuple((unsigned_hash >> (band * BAND_BITS)) & 255 for band in range(BANDS))


def similarity_pct(distance: int) -> int:
    return round((HASH_BITS - distance) / HASH_BITS * 100)


def _connected_components(values: list[int], threshold: int) -> list[list[int]]:
    """Union-find over distinct hash values using banded candidate pairs."""
    parent: dict[int, int] = {value: value for value in values}

    def find(value: int) -> int:
        root = value
        while parent[root] != root:
            root = parent[root]
        while parent[value] != root:  # path compression
            parent[value], value = root, parent[value]
        return root

    buckets: dict[tuple[int, int], list[int]] = {}
    for value in values:
        for band, band_value in enumerate(band_values(value)):
            buckets.setdefault((band, band_value), []).append(value)

    checked: set[tuple[int, int]] = set()
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for i, first in enumerate(bucket):
            for second in bucket[i + 1 :]:
                pair = (first, second) if first < second else (second, first)
                if pair in checked:
                    continue
                checked.add(pair)
                if (first ^ second).bit_count() <= threshold:
                    root_a, root_b = find(first), find(second)
                    if root_a != root_b:
                        parent[root_b] = root_a

    components: dict[int, list[int]] = {}
    for value in values:
        components.setdefault(find(value), []).append(value)
    return [component for component in components.values() if len(component) >= 1]


def derive_similar_groups(photos: list[PhotoInfo], threshold: int) -> list[DerivedGroup]:
    """Group visually similar photos; components that are all byte-identical
    copies are excluded (the exact-duplicate pass owns those)."""
    hashed = [p for p in photos if p.phash is not None and p.sha256 is not None]
    by_value: dict[int, list[PhotoInfo]] = {}
    for photo in hashed:
        assert photo.phash is not None
        by_value.setdefault(to_unsigned(photo.phash), []).append(photo)

    groups: list[DerivedGroup] = []
    for component in _connected_components(list(by_value), threshold):
        members = [photo for value in component for photo in by_value[value]]
        if len(members) < 2:
            continue
        distinct_shas = {photo.sha256 for photo in members}
        if len(distinct_shas) < 2:
            continue  # purely exact copies
        keeper = keeper_of(members)
        assert keeper.phash is not None
        keeper_hash = to_unsigned(keeper.phash)
        groups.append(
            DerivedGroup(
                kind="similar",
                key=min(sha for sha in distinct_shas if sha is not None),
                keeper_photo_id=keeper.id,
                members={
                    photo.id: similarity_pct(hamming(photo.phash or 0, keeper_hash))
                    for photo in members
                },
            )
        )
    return groups
