"""Duplicate-group lifecycle: rebuild after scans, review decisions.

Both rebuilds re-derive groups from active photos and sync by the stable
(kind, key) identity. Unchanged groups keep their id, status, and decisions;
groups whose membership changed drop back to 'pending' (a new copy appearing in
a reviewed group needs another look). Decisions for photos that left a group are
deleted.

`rebuild_duplicate_groups` does the whole library — correct by construction, and
O(n^2/64) in distance checks. `rebuild_groups_for` does the same work over a
closed subgraph around what a scan changed, which is what scans use until a
change is broad enough that bounding stops paying. See
docs/ARCHITECTURE.md#the-bounded-rebuild.
"""

import logging
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.config import get_settings
from app.dedupe.grouping import DerivedGroup, PhotoInfo, derive_exact_groups
from app.dedupe.similarity import BANDS, derive_similar_groups
from app.models import (
    DuplicateDecision,
    DuplicateGroup,
    DuplicateGroupMember,
    Photo,
)
from app.models.duplicates import DECISIONS
from app.repositories.duplicates import DuplicateRepository
from app.services.errors import NotFoundError, ValidationFailedError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RebuildResult:
    exact_groups: int
    similar_groups: int


def _load_photo_infos(session: Session) -> list[PhotoInfo]:
    rows = session.execute(
        select(
            Photo.id, Photo.sha256, Photo.phash, Photo.size_bytes, Photo.width, Photo.height
        ).where(Photo.status == "active")
    )
    return [PhotoInfo(*row) for row in rows]


def derive_groups(photos: list[PhotoInfo]) -> list[DerivedGroup]:
    threshold = get_settings().similar_hamming_threshold
    return derive_exact_groups(photos) + derive_similar_groups(photos, threshold)


def rebuild_duplicate_groups(session: Session) -> RebuildResult:
    photos = _load_photo_infos(session)
    derived = derive_groups(photos)
    derived_by_identity = {(g.kind, g.key): g for g in derived}

    existing = session.scalars(
        select(DuplicateGroup).options(selectinload(DuplicateGroup.members))
    ).all()

    for group in existing:
        target = derived_by_identity.pop((group.kind, group.key), None)
        if target is None:
            session.delete(group)  # no longer a duplicate set
            continue
        _sync_group(session, group, target)

    for target in derived_by_identity.values():
        group = DuplicateGroup(
            kind=target.kind, key=target.key, keeper_photo_id=target.keeper_photo_id
        )
        group.members = [
            DuplicateGroupMember(photo_id=photo_id, similarity_pct=pct)
            for photo_id, pct in sorted(target.members.items())
        ]
        session.add(group)

    session.commit()
    result = RebuildResult(
        exact_groups=sum(1 for g in derived if g.kind == "exact"),
        similar_groups=sum(1 for g in derived if g.kind == "similar"),
    )
    logger.info(
        "duplicate rebuild: %d exact, %d similar groups",
        result.exact_groups,
        result.similar_groups,
    )
    return result


# Postgres copes with large IN lists, but the planner degrades and the statement
# gets unreasonable to read in a trace. Well above any realistic touched set.
_ID_CHUNK = 5_000


def _in_chunks(ids: Sequence[int]) -> Iterator[Sequence[int]]:
    for start in range(0, len(ids), _ID_CHUNK):
        yield ids[start : start + _ID_CHUNK]


def _neighbour_ids(session: Session, seed_ids: Sequence[int]) -> set[int]:
    """Active photos genuinely within the similarity threshold of any seed.

    Band equality alone is *not* usable here. It is a candidate filter with a
    ~1/32 false-positive rate per pair, which is fine when checking one hash but
    catastrophic in bulk: collect the band values of 200 seeds and each of the
    eight 8-bit bands covers most of its 256 possible values, so nearly every
    photo in the library "matches" and the subgraph stops being a subgraph.

    So the distance check happens here, in SQL, over the same indexed bands the
    lightbox's "more like this" uses. Postgres narrows by band equality then
    verifies with bit_count, one query per band regardless of how many seeds —
    the work is the inherent candidate count, k*n/32, not k*n.
    """
    threshold = get_settings().similar_hamming_threshold
    other = aliased(Photo)
    found: set[int] = set()

    for chunk in _in_chunks(seed_ids):
        for band in range(BANDS):
            column = f"phash_b{band}"
            found.update(
                session.scalars(
                    select(Photo.id)
                    .join(other, getattr(Photo, column) == getattr(other, column))
                    .where(
                        other.id.in_(chunk),
                        Photo.status == "active",
                        Photo.id != other.id,
                        func.bit_count(cast(Photo.phash.op("#")(other.phash), BIT(64)))
                        <= threshold,
                    )
                ).all()
            )
        # Byte-identical copies still group even when the pHash never computed.
        shas = set(
            session.scalars(
                select(Photo.sha256).where(Photo.id.in_(chunk), Photo.sha256.is_not(None))
            ).all()
        )
        if shas:
            found.update(
                session.scalars(
                    select(Photo.id).where(Photo.status == "active", Photo.sha256.in_(shas))
                ).all()
            )
    return found


def _sha_mates(session: Session, photo_ids: Sequence[int]) -> set[int]:
    """Every active photo sharing a sha256 with one of `photo_ids`.

    Belt and braces. An exact group must be re-derived from *all* its copies or
    _sync_group would read the missing ones as departures and evict them. Copies
    are byte-identical so they share a pHash and _neighbour_ids already finds
    them — unless the pHash never computed, which this covers without needing
    that argument to hold.
    """
    found: set[int] = set()
    for chunk in _in_chunks(photo_ids):
        shas = set(
            session.scalars(
                select(Photo.sha256).where(Photo.id.in_(chunk), Photo.sha256.is_not(None))
            ).all()
        )
        if not shas:
            continue
        found.update(
            session.scalars(
                select(Photo.id).where(Photo.status == "active", Photo.sha256.in_(shas))
            ).all()
        )
    return found


def _groups_touching(session: Session, photo_ids: Sequence[int]) -> set[int]:
    found: set[int] = set()
    for chunk in _in_chunks(photo_ids):
        found.update(
            session.scalars(
                select(DuplicateGroupMember.group_id).where(
                    DuplicateGroupMember.photo_id.in_(chunk)
                )
            ).all()
        )
    return found


def _members_of(session: Session, group_ids: Sequence[int]) -> set[int]:
    found: set[int] = set()
    for chunk in _in_chunks(group_ids):
        found.update(
            session.scalars(
                select(DuplicateGroupMember.photo_id).where(
                    DuplicateGroupMember.group_id.in_(chunk)
                )
            ).all()
        )
    return found


def _infos_for(session: Session, photo_ids: Sequence[int]) -> list[PhotoInfo]:
    infos: list[PhotoInfo] = []
    for chunk in _in_chunks(photo_ids):
        infos.extend(
            PhotoInfo(*row)
            for row in session.execute(
                select(
                    Photo.id, Photo.sha256, Photo.phash, Photo.size_bytes, Photo.width, Photo.height
                ).where(Photo.id.in_(chunk), Photo.status == "active")
            )
        )
    return infos


def rebuild_groups_for(session: Session, touched_ids: Collection[int]) -> RebuildResult:
    """Re-derive only the groups the touched photos can affect.

    The full pass is O(n^2/64) in distance checks, so a scan that adds a handful
    of photos to a large library pays for the whole library. This bounds the work
    to a subgraph and leaves every group outside it alone.

    The subgraph has to be *closed* — it must contain whole components, or
    derivation would split a group that merely extends past the edge. Built as:

        candidates = touched + their band/sha neighbours + those neighbours' sha copies
        subgraph   = candidates + every member of every group a candidate belongs to

    Seeding scope from candidates rather than from the touched photos alone is
    what makes it correct: a newly added photo is in no group yet, so its future
    group is only reachable through the neighbour it will join. Components are
    maximal, so nothing outside the subgraph can be within the threshold of
    anything inside it, and adding photos only ever merges components — never
    splits one, which is what would require looking further out.

    Groups are synced by the same (kind, key) identity the full pass uses, so
    ids, review status and decisions survive exactly as they do there. Unlike
    the full pass, a group absent from the derivation is only deleted when it
    was in scope — otherwise every untouched group in the library would be.

    Returns counts for the affected subgraph, not the library.
    """
    touched = sorted(set(touched_ids))
    if not touched:
        return RebuildResult(exact_groups=0, similar_groups=0)

    candidates = set(touched) | _neighbour_ids(session, touched)
    candidates |= _sha_mates(session, sorted(candidates))

    scope_group_ids = _groups_touching(session, sorted(candidates))
    subgraph_ids = candidates | _members_of(session, sorted(scope_group_ids))

    photos = _infos_for(session, sorted(subgraph_ids))
    derived = derive_groups(photos)
    derived_by_identity = {(g.kind, g.key): g for g in derived}

    # Groups reachable two ways: by containing a subgraph photo, and by matching
    # a derived identity. The second catches a group whose members all left the
    # active set — its key can still be re-derived here, and creating a second
    # row with the same identity would break the (kind, key) invariant.
    in_scope = scope_group_ids | _groups_touching(session, sorted(subgraph_ids))
    existing = list(
        session.scalars(
            select(DuplicateGroup)
            .options(selectinload(DuplicateGroup.members))
            .where(DuplicateGroup.id.in_(sorted(in_scope)))
        ).all()
    )
    seen_ids = {group.id for group in existing}
    for kind, key in derived_by_identity:
        match = session.scalar(
            select(DuplicateGroup)
            .options(selectinload(DuplicateGroup.members))
            .where(DuplicateGroup.kind == kind, DuplicateGroup.key == key)
        )
        if match is not None and match.id not in seen_ids:
            existing.append(match)
            seen_ids.add(match.id)

    for group in existing:
        target = derived_by_identity.pop((group.kind, group.key), None)
        if target is None:
            session.delete(group)
            continue
        _sync_group(session, group, target)

    for target in derived_by_identity.values():
        group = DuplicateGroup(
            kind=target.kind, key=target.key, keeper_photo_id=target.keeper_photo_id
        )
        group.members = [
            DuplicateGroupMember(photo_id=photo_id, similarity_pct=pct)
            for photo_id, pct in sorted(target.members.items())
        ]
        session.add(group)

    session.commit()
    result = RebuildResult(
        exact_groups=sum(1 for g in derived if g.kind == "exact"),
        similar_groups=sum(1 for g in derived if g.kind == "similar"),
    )
    logger.info(
        "bounded duplicate rebuild: %d touched photo(s) -> %d in subgraph, "
        "%d group(s) in scope, derived %d exact / %d similar",
        len(touched),
        len(subgraph_ids),
        len(in_scope),
        result.exact_groups,
        result.similar_groups,
    )
    return result


def _sync_group(session: Session, group: DuplicateGroup, target: DerivedGroup) -> None:
    current_ids = {member.photo_id for member in group.members}
    target_ids = set(target.members)

    if current_ids != target_ids:
        # Membership changed: review state is stale.
        group.status = "pending" if group.status == "reviewed" else group.status
        for member in list(group.members):
            if member.photo_id not in target_ids:
                group.members.remove(member)
        session.flush()
        departed = current_ids - target_ids
        if departed:
            for decision in session.scalars(
                select(DuplicateDecision).where(
                    DuplicateDecision.group_id == group.id,
                    DuplicateDecision.photo_id.in_(departed),
                )
            ):
                session.delete(decision)
        for photo_id in target_ids - current_ids:
            group.members.append(
                DuplicateGroupMember(photo_id=photo_id, similarity_pct=target.members[photo_id])
            )
    for member in group.members:
        member.similarity_pct = target.members[member.photo_id]
    group.keeper_photo_id = target.keeper_photo_id


class DuplicateService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = DuplicateRepository(session)

    def list_groups(
        self, kind: str | None, status: str | None, limit: int, offset: int
    ) -> tuple[list[DuplicateGroup], int]:
        groups, total = self._repo.list_groups(kind=kind, status=status, limit=limit, offset=offset)
        return list(groups), total

    def get_group(self, group_id: int) -> DuplicateGroup:
        group = self._repo.get(group_id)
        if group is None:
            raise NotFoundError(f"Duplicate group {group_id} not found")
        return group

    def decide(
        self, group_id: int, decisions: list[tuple[int, str]], force: bool = False
    ) -> DuplicateGroup:
        group = self.get_group(group_id)
        member_ids = {member.photo_id for member in group.members}
        for photo_id, decision in decisions:
            if photo_id not in member_ids:
                raise ValidationFailedError(f"Photo {photo_id} is not a member of group {group_id}")
            if decision not in (*DECISIONS, "undecided"):
                raise ValidationFailedError(f"Unknown decision: {decision}")
        if (
            not force
            and all(decision == "remove" for _, decision in decisions)
            and {photo_id for photo_id, _ in decisions} == member_ids
        ):
            raise ValidationFailedError(
                "Refusing to mark every photo in the group for removal — keep at least one "
                "(pass force to remove them all)"
            )

        self._repo.apply_decisions(group, decisions)
        decided = self._repo.decisions_for(group.id)
        group.status = "reviewed" if member_ids <= set(decided) else "pending"
        self._session.commit()
        self._session.refresh(group)
        return group

    def dismiss(self, group_id: int) -> DuplicateGroup:
        group = self.get_group(group_id)
        group.status = "dismissed"
        self._session.commit()
        return group

    def reopen(self, group_id: int) -> DuplicateGroup:
        """Return a reviewed or dismissed group to 'pending' for another look.

        Decisions are cleared so the review flow presents every pair fresh.
        Safe: quarantine/deletion is a separate step, so a 'reviewed' group
        still has all its files on disk.
        """
        group = self.get_group(group_id)
        for decision in list(group.decisions):
            self._session.delete(decision)
        group.status = "pending"
        self._session.commit()
        self._session.refresh(group)
        return group
