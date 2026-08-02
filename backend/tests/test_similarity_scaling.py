"""The LSH grouping stays correct and stays within memory as the library grows.

The pass is quadratic in comparisons within a band bucket — inherent to being
complete for threshold <= 7 — so the thing that has to hold at 50k photos is
memory. An earlier version memoized every compared pair and peaked at 418 MB
by n=18,000, projecting past 3 GB; union-find already makes repeated merges
idempotent, so that bookkeeping was both costly and unnecessary.
"""

import random
import tracemalloc

from app.dedupe.similarity import _connected_components


def _brute_force_components(values: list[int], threshold: int) -> list[tuple[int, ...]]:
    """Transitive closure of "within threshold", comparing every pair directly.

    The reference the banded shortcut has to match: banding is only a way to
    skip pairs that cannot be close, so it must find the same components.
    """
    parent = {value: value for value in values}

    def find(value: int) -> int:
        while parent[value] != value:
            value = parent[value]
        return value

    for i, first in enumerate(values):
        for second in values[i + 1 :]:
            if (first ^ second).bit_count() <= threshold:
                root_a, root_b = find(first), find(second)
                if root_a != root_b:
                    parent[root_b] = root_a

    groups: dict[int, list[int]] = {}
    for value in values:
        groups.setdefault(find(value), []).append(value)
    return sorted(tuple(sorted(group)) for group in groups.values())


def _normalize(components: list[list[int]]) -> list[tuple[int, ...]]:
    return sorted(tuple(sorted(component)) for component in components)


def _spread(seed: int, count: int) -> list[int]:
    random.seed(seed)
    return [random.getrandbits(64) for _ in range(count)]


def _clustered(seed: int) -> list[int]:
    """Burst-shot shaped input: tight clusters a few bit-flips apart."""
    random.seed(seed)
    bases = [random.getrandbits(64) for _ in range(12)]
    return list(
        {
            base ^ (1 << random.randrange(64)) ^ (1 << random.randrange(64))
            for base in bases
            for _ in range(12)
        }
    )


def test_banding_finds_the_same_components_as_comparing_every_pair() -> None:
    for seed in range(12):
        values = _spread(seed, 300) if seed % 2 else _clustered(seed)
        for threshold in (0, 3, 6, 7):
            assert _normalize(_connected_components(values, threshold)) == _brute_force_components(
                values, threshold
            ), f"seed={seed} threshold={threshold}"


def test_photos_only_group_when_they_are_actually_close() -> None:
    base = 0x1234_5678_9ABC_DEF0
    near = base ^ 0b111  # distance 3
    far = ~base & ((1 << 64) - 1)  # distance 64

    components = _normalize(_connected_components([base, near, far], 6))

    assert components == sorted([tuple(sorted((base, near))), (far,)])


def test_grouping_memory_stays_flat_as_the_library_grows() -> None:
    """Linear, not quadratic — this is what has to hold at 50k photos."""
    peaks = []
    for count in (4000, 8000):
        values = _spread(1, count)
        tracemalloc.start()
        try:
            _connected_components(values, 6)
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()

    small, large = peaks
    # Doubling n must not quadruple memory. The pair-memoizing version grew
    # ~4x per doubling (27 MB -> 106 MB -> 418 MB); this stays in single MB.
    assert large < small * 3, f"memory grew {large / small:.1f}x when n doubled"
    assert large < 40_000_000, f"peak {large / 1e6:.1f} MB at n=8000 is too high"
