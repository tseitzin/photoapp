from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.photo import Photo

DUPLICATE_KINDS = ("exact", "similar")
GROUP_STATUSES = ("pending", "reviewed", "dismissed")
DECISIONS = ("keep", "remove")


class DuplicateGroup(Base):
    """A set of photos believed to be copies of each other.

    Identity survives rebuilds via (kind, key): exact groups are keyed by the
    shared sha256, similar groups by the smallest sha256 in the component —
    so review state is preserved when a scan re-derives the same group.
    """

    __tablename__ = "duplicate_groups"
    __table_args__ = (UniqueConstraint("kind", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)
    key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(10), default="pending", server_default="pending", index=True
    )
    keeper_photo_id: Mapped[int | None] = mapped_column(
        ForeignKey("photos.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["DuplicateGroupMember"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="DuplicateGroupMember.photo_id",
    )
    decisions: Mapped[list["DuplicateDecision"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class DuplicateGroupMember(Base):
    __tablename__ = "duplicate_group_members"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("duplicate_groups.id", ondelete="CASCADE"), primary_key=True
    )
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    # 100 = byte-identical; similar members scored by Hamming distance to the keeper.
    similarity_pct: Mapped[int]

    group: Mapped[DuplicateGroup] = relationship(back_populates="members")
    photo: Mapped[Photo] = relationship()


class DuplicateDecision(Base):
    """The user's per-photo review choice. 'undecided' is the absence of a row."""

    __tablename__ = "duplicate_decisions"
    __table_args__ = (UniqueConstraint("group_id", "photo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("duplicate_groups.id", ondelete="CASCADE"), index=True
    )
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"))
    decision: Mapped[str] = mapped_column(String(10))
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    group: Mapped[DuplicateGroup] = relationship(back_populates="decisions")
