from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models import DuplicateGroup
from app.schemas.photos import PhotoRead

DuplicateKind = Literal["exact", "similar"]
GroupStatus = Literal["pending", "reviewed", "dismissed"]
Decision = Literal["keep", "remove", "undecided"]


class DuplicateMemberRead(BaseModel):
    photo: PhotoRead
    similarity_pct: int
    decision: Literal["keep", "remove"] | None


class DuplicateGroupRead(BaseModel):
    id: int
    kind: DuplicateKind
    status: GroupStatus
    keeper_photo_id: int | None
    members: list[DuplicateMemberRead]
    reclaimable_bytes: int
    created_at: datetime

    @classmethod
    def from_group(cls, group: DuplicateGroup) -> "DuplicateGroupRead":
        decisions = {d.photo_id: d.decision for d in group.decisions}
        members = [
            DuplicateMemberRead(
                photo=PhotoRead.model_validate(member.photo),
                similarity_pct=member.similarity_pct,
                decision=decisions.get(member.photo_id),
            )
            for member in group.members
        ]
        total = sum(m.photo.size_bytes for m in members)
        keeper_size = next(
            (m.photo.size_bytes for m in members if m.photo.id == group.keeper_photo_id),
            max((m.photo.size_bytes for m in members), default=0),
        )
        return cls(
            id=group.id,
            kind=group.kind,
            status=group.status,
            keeper_photo_id=group.keeper_photo_id,
            members=members,
            reclaimable_bytes=max(0, total - keeper_size),
            created_at=group.created_at,
        )


class DuplicateGroupPage(BaseModel):
    items: list[DuplicateGroupRead]
    total: int
    limit: int
    offset: int


class DecisionWrite(BaseModel):
    photo_id: int
    decision: Decision


class DecisionsWrite(BaseModel):
    decisions: list[DecisionWrite]


class DuplicateSummary(BaseModel):
    groups: int
    pending_groups: int
    reviewed_groups: int
    dismissed_groups: int
    exact_groups: int
    similar_groups: int
    member_photos: int
    marked_remove_count: int
    marked_remove_bytes: int


class RebuildRead(BaseModel):
    exact_groups: int
    similar_groups: int
