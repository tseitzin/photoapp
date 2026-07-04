"""Duplicate-group lifecycle: rebuild after scans, review decisions.

Rebuild strategy (v1): re-derive all groups from active photos and sync by the
stable (kind, key) identity. Unchanged groups keep their id, status, and
decisions; groups whose membership changed drop back to 'pending' (a new copy
appearing in a reviewed group needs another look). Decisions for photos that
left a group are deleted.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.dedupe.grouping import DerivedGroup, PhotoInfo, derive_exact_groups
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
    return derive_exact_groups(photos)


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

    def decide(self, group_id: int, decisions: list[tuple[int, str]]) -> DuplicateGroup:
        group = self.get_group(group_id)
        member_ids = {member.photo_id for member in group.members}
        for photo_id, decision in decisions:
            if photo_id not in member_ids:
                raise ValidationFailedError(f"Photo {photo_id} is not a member of group {group_id}")
            if decision not in (*DECISIONS, "undecided"):
                raise ValidationFailedError(f"Unknown decision: {decision}")
        if (
            all(decision == "remove" for _, decision in decisions)
            and {photo_id for photo_id, _ in decisions} == member_ids
        ):
            raise ValidationFailedError(
                "Refusing to mark every photo in the group for removal — keep at least one"
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
