from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import DuplicateDecision, DuplicateGroup, DuplicateGroupMember, Photo


class DuplicateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _loaded(self) -> Select[tuple[DuplicateGroup]]:
        return select(DuplicateGroup).options(
            selectinload(DuplicateGroup.members).selectinload(DuplicateGroupMember.photo),
            selectinload(DuplicateGroup.decisions),
        )

    def get(self, group_id: int) -> DuplicateGroup | None:
        return self._session.scalar(self._loaded().where(DuplicateGroup.id == group_id))

    def list_groups(
        self, kind: str | None, status: str | None, limit: int, offset: int
    ) -> tuple[Sequence[DuplicateGroup], int]:
        conditions = []
        if kind is not None:
            conditions.append(DuplicateGroup.kind == kind)
        if status is not None:
            conditions.append(DuplicateGroup.status == status)
        total = (
            self._session.scalar(
                select(func.count()).select_from(DuplicateGroup).where(*conditions)
            )
            or 0
        )
        groups = self._session.scalars(
            self._loaded()
            .where(*conditions)
            .order_by(DuplicateGroup.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return groups, total

    def non_keeper_exact_member_ids(self, photo_ids: Sequence[int]) -> set[int]:
        """Of the given photos, those that are redundant copies in an exact group
        (members that are not the group's keeper)."""
        if not photo_ids:
            return set()
        return set(
            self._session.scalars(
                select(DuplicateGroupMember.photo_id)
                .join(DuplicateGroup, DuplicateGroup.id == DuplicateGroupMember.group_id)
                .where(
                    DuplicateGroup.kind == "exact",
                    DuplicateGroupMember.photo_id.in_(list(photo_ids)),
                    DuplicateGroupMember.photo_id != DuplicateGroup.keeper_photo_id,
                )
            )
        )

    def decisions_for(self, group_id: int) -> dict[int, str]:
        rows = self._session.execute(
            select(DuplicateDecision.photo_id, DuplicateDecision.decision).where(
                DuplicateDecision.group_id == group_id
            )
        )
        return {photo_id: decision for photo_id, decision in rows.all()}

    def apply_decisions(self, group: DuplicateGroup, decisions: list[tuple[int, str]]) -> None:
        existing = {
            decision.photo_id: decision
            for decision in self._session.scalars(
                select(DuplicateDecision).where(DuplicateDecision.group_id == group.id)
            )
        }
        for photo_id, decision in decisions:
            row = existing.get(photo_id)
            if decision == "undecided":
                if row is not None:
                    self._session.delete(row)
            elif row is not None:
                row.decision = decision
            else:
                self._session.add(
                    DuplicateDecision(group_id=group.id, photo_id=photo_id, decision=decision)
                )
        self._session.flush()

    def summary(self) -> dict[str, int]:
        def count(*conditions: object) -> int:
            return (
                self._session.scalar(
                    select(func.count()).select_from(DuplicateGroup).where(*conditions)  # type: ignore[arg-type]
                )
                or 0
            )

        marked = self._session.execute(
            select(func.count(), func.coalesce(func.sum(Photo.size_bytes), 0))
            .select_from(DuplicateDecision)
            .join(Photo, Photo.id == DuplicateDecision.photo_id)
            .where(DuplicateDecision.decision == "remove")
        ).one()

        duplicate_photos = (
            self._session.scalar(select(func.count()).select_from(DuplicateGroupMember)) or 0
        )

        return {
            "groups": count(),
            "pending_groups": count(DuplicateGroup.status == "pending"),
            "reviewed_groups": count(DuplicateGroup.status == "reviewed"),
            "dismissed_groups": count(DuplicateGroup.status == "dismissed"),
            "exact_groups": count(DuplicateGroup.kind == "exact"),
            "similar_groups": count(DuplicateGroup.kind == "similar"),
            "member_photos": duplicate_photos,
            "marked_remove_count": int(marked[0]),
            "marked_remove_bytes": int(marked[1]),
        }
