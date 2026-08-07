"""The bounded duplicate rebuild agrees with the full one, at a fraction of the cost.

The full pass re-derives every group from every active photo, which is O(n^2/64)
distance checks — an import of a few hundred photos into a large library used to
pay for every photo already indexed. The bounded pass derives only a closed
subgraph around what changed.

Correctness here means one thing above all: the two passes must produce the same
groups. `test_bounded_and_full_rebuilds_agree` is the load-bearing test — the
others name the specific ways a naive bounding would go wrong, so a failure
points at the cause rather than just the symptom.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DuplicateGroup, Photo, ScanRoot
from app.services.duplicates import rebuild_duplicate_groups, rebuild_groups_for
from tests.images import make_textured_image

# A hash far from BASE in every band, so the two never share a candidate bucket.
BASE = 0x0F0F_0F0F_0F0F_0F0F
FAR = 0x5A5A_5A5A_5A5A_5A5A


def near(value: int, bits: int) -> int:
    """`value` with `bits` low bits flipped — Hamming distance exactly `bits`."""
    return value ^ ((1 << bits) - 1)


@pytest.fixture
def root(db_session: Session) -> ScanRoot:
    scan_root = ScanRoot(path="/nowhere/real", enabled=True)
    db_session.add(scan_root)
    db_session.commit()
    return scan_root


@pytest.fixture
def add_photo(db_session: Session, root: ScanRoot) -> Callable[..., Photo]:
    counter = {"n": 0}

    def _add(sha256: str, phash: int | None, *, size_bytes: int = 1000) -> Photo:
        counter["n"] += 1
        n = counter["n"]
        photo = Photo(
            root_id=root.id,
            path=f"/nowhere/real/photo_{n}.jpg",
            filename=f"photo_{n}.jpg",
            ext="jpg",
            mime="image/jpeg",
            size_bytes=size_bytes,
            mtime_ns=n,
            status="active",
            sha256=sha256,
            phash=phash,
            width=100,
            height=100,
        )
        db_session.add(photo)
        db_session.commit()
        return photo

    return _add


def snapshot(session: Session) -> set[tuple[str, str, int, frozenset[tuple[int, int]]]]:
    """Group state in a form two derivations can be compared by."""
    return {
        (
            group.kind,
            group.key,
            group.keeper_photo_id,
            frozenset((m.photo_id, m.similarity_pct) for m in group.members),
        )
        for group in session.scalars(select(DuplicateGroup)).all()
    }


def test_bounded_and_full_rebuilds_agree(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    """The property the whole optimisation rests on.

    A library with every shape that matters — exact copies, a similar cluster, a
    photo bridging two clusters, and untouched singletons — then an import, then
    both passes compared.
    """
    add_photo("sha-a", BASE)
    add_photo("sha-a", BASE)  # exact copy of the above
    add_photo("sha-b", near(BASE, 3))  # similar to the pair
    add_photo("sha-c", FAR)  # unrelated cluster seed
    add_photo("sha-d", near(FAR, 2))  # similar to sha-c
    add_photo("sha-e", 0x1234_5678_9ABC_DEF0)  # singleton, never touched
    rebuild_duplicate_groups(db_session)

    imported = [
        add_photo("sha-f", near(BASE, 5)).id,  # extends the BASE cluster
        add_photo("sha-a", BASE).id,  # a third byte-identical copy
        add_photo("sha-g", near(FAR, 4)).id,  # extends the FAR cluster
    ]
    rebuild_groups_for(db_session, imported)
    bounded = snapshot(db_session)

    rebuild_duplicate_groups(db_session)

    assert bounded == snapshot(db_session)


def test_a_new_copy_joins_the_exact_group_it_duplicates(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    add_photo("sha-a", BASE)
    add_photo("sha-a", BASE)
    rebuild_duplicate_groups(db_session)

    third = add_photo("sha-a", BASE)
    rebuild_groups_for(db_session, [third.id])

    group = db_session.scalar(select(DuplicateGroup).where(DuplicateGroup.kind == "exact"))
    assert group is not None
    assert {m.photo_id for m in group.members} == {p.id for p in db_session.scalars(select(Photo))}


def test_a_new_similar_photo_forms_a_similar_group(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    """The regression an exact-only incremental path would cause.

    add_photos_to_groups (the quarantine-restore path) re-forms exact groups
    only. Routing imports through it would leave every newly added photo out of
    "visually similar" until the next full rebuild.
    """
    existing = add_photo("sha-a", BASE)
    rebuild_duplicate_groups(db_session)
    assert db_session.scalar(select(DuplicateGroup)) is None  # a lone photo groups with nothing

    variant = add_photo("sha-b", near(BASE, 3))
    rebuild_groups_for(db_session, [variant.id])

    group = db_session.scalar(select(DuplicateGroup).where(DuplicateGroup.kind == "similar"))
    assert group is not None
    assert {m.photo_id for m in group.members} == {existing.id, variant.id}


def test_a_photo_bridging_two_clusters_merges_them(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    """The component-merge case the original incremental path deliberately avoided.

    Two clusters sit 8 bits apart — past the threshold of 6, so they are separate
    groups. A photo 4 bits from each connects them into one component, which only
    comes out right if the subgraph pulls in *both* whole groups rather than just
    the neighbours the bridge happens to touch.
    """
    left, left_mate = add_photo("sha-a", BASE), add_photo("sha-b", near(BASE, 2))
    right_base = BASE ^ 0xFF00  # 8 bits from BASE: too far to be one group
    right, right_mate = add_photo("sha-c", right_base), add_photo("sha-d", right_base ^ 0b11)
    rebuild_duplicate_groups(db_session)
    assert len(list(db_session.scalars(select(DuplicateGroup)))) == 2

    bridge = add_photo("sha-e", BASE ^ 0xF000)  # 4 bits from each side
    rebuild_groups_for(db_session, [bridge.id])

    groups = list(db_session.scalars(select(DuplicateGroup)))
    assert len(groups) == 1
    assert {m.photo_id for m in groups[0].members} == {
        left.id,
        left_mate.id,
        right.id,
        right_mate.id,
        bridge.id,
    }


def test_groups_outside_the_subgraph_keep_their_identity(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    """The whole point of bounding: untouched groups are not rederived.

    A full rebuild reassigns nothing but does re-sync every group; the bounded
    pass must not even load them, and must never delete one merely because it is
    absent from a derivation that never considered it.
    """
    add_photo("sha-x", FAR)
    add_photo("sha-x", FAR)
    rebuild_duplicate_groups(db_session)
    untouched = db_session.scalar(select(DuplicateGroup))
    assert untouched is not None
    untouched_id, untouched_key = untouched.id, untouched.key

    newcomer = add_photo("sha-y", BASE)
    rebuild_groups_for(db_session, [newcomer.id])

    survivor = db_session.get(DuplicateGroup, untouched_id)
    assert survivor is not None
    assert survivor.key == untouched_key
    assert len(survivor.members) == 2


def test_a_review_decision_survives_an_unrelated_import(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    """Group ids are stable across the bounded pass, so decisions keep pointing
    at something real — the same guarantee the full pass gives."""
    add_photo("sha-x", FAR)
    add_photo("sha-x", FAR)
    rebuild_duplicate_groups(db_session)
    group = db_session.scalar(select(DuplicateGroup))
    assert group is not None
    group.status = "reviewed"
    db_session.commit()

    rebuild_groups_for(db_session, [add_photo("sha-y", BASE).id])

    db_session.refresh(group)
    assert group.status == "reviewed"


def test_a_photo_leaving_the_active_set_shrinks_its_group(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    """A scan marks vanished files 'missing'; their groups must follow."""
    keep, keep_two = add_photo("sha-a", BASE), add_photo("sha-a", BASE)
    add_photo("sha-a", BASE)
    rebuild_duplicate_groups(db_session)
    gone = db_session.scalar(select(Photo).where(Photo.id.not_in([keep.id, keep_two.id])))
    assert gone is not None

    gone.status = "missing"
    db_session.commit()
    rebuild_groups_for(db_session, [gone.id])

    group = db_session.scalar(select(DuplicateGroup))
    assert group is not None
    assert {m.photo_id for m in group.members} == {keep.id, keep_two.id}


def test_the_last_pair_member_leaving_dissolves_the_group(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    add_photo("sha-a", BASE)
    gone = add_photo("sha-a", BASE)
    rebuild_duplicate_groups(db_session)
    assert db_session.scalar(select(DuplicateGroup)) is not None

    gone.status = "missing"
    db_session.commit()
    rebuild_groups_for(db_session, [gone.id])

    assert db_session.scalar(select(DuplicateGroup)) is None


def test_touching_nothing_changes_nothing(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    add_photo("sha-a", BASE)
    add_photo("sha-a", BASE)
    rebuild_duplicate_groups(db_session)
    before = snapshot(db_session)

    result = rebuild_groups_for(db_session, [])

    assert result.exact_groups == 0 and result.similar_groups == 0
    assert snapshot(db_session) == before


def test_a_photo_without_a_phash_still_joins_its_exact_group(
    db_session: Session, add_photo: Callable[..., Photo]
) -> None:
    """pHash can be absent when decoding failed. Candidate lookup falls back to
    sha256, so byte-identical copies still group."""
    first = add_photo("sha-a", None)
    rebuild_duplicate_groups(db_session)

    second = add_photo("sha-a", None)
    rebuild_groups_for(db_session, [second.id])

    group = db_session.scalar(select(DuplicateGroup))
    assert group is not None
    assert {m.photo_id for m in group.members} == {first.id, second.id}


def _scan(client: TestClient) -> None:
    assert client.post("/api/scans", json={}).status_code == 202


def test_a_rescan_that_adds_one_photo_still_groups_it(client: TestClient, tmp_path: Path) -> None:
    """End to end through the scan, on the path that actually bounds the work.

    A first scan adds every photo, so it exceeds the touched share and falls back
    to the full pass — only a rescan of an established library exercises the
    bounded one. The added file is a resized copy of an indexed photo, so it must
    land in a *similar* group: the case an exact-only incremental path would miss.
    """
    make_textured_image(tmp_path / "original.jpg", seed=7, size=(800, 600))
    for seed in (1, 2, 3):
        make_textured_image(tmp_path / f"other_{seed}.jpg", seed=seed)
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    _scan(client)
    assert client.get("/api/duplicates/groups", params={"kind": "similar"}).json()["total"] == 0

    make_textured_image(tmp_path / "resized.jpg", seed=7, size=(400, 300), quality=70)
    _scan(client)

    similar = client.get("/api/duplicates/groups", params={"kind": "similar"}).json()
    assert similar["total"] == 1
    assert {m["photo"]["filename"] for m in similar["items"][0]["members"]} == {
        "original.jpg",
        "resized.jpg",
    }


def test_a_rescan_that_adds_an_identical_copy_groups_it_as_exact(
    client: TestClient, tmp_path: Path
) -> None:
    original = make_textured_image(tmp_path / "original.jpg", seed=7, size=(800, 600))
    for seed in (1, 2, 3):
        make_textured_image(tmp_path / f"other_{seed}.jpg", seed=seed)
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    _scan(client)

    (tmp_path / "copy.jpg").write_bytes(original.read_bytes())
    _scan(client)

    exact = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()
    assert exact["total"] == 1
    assert {m["photo"]["filename"] for m in exact["items"][0]["members"]} == {
        "original.jpg",
        "copy.jpg",
    }
