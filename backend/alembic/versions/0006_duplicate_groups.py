"""Duplicate groups, members, and review decisions.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "duplicate_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="pending"),
        sa.Column(
            "keeper_photo_id",
            sa.Integer(),
            sa.ForeignKey("photos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("kind", "key"),
    )
    op.create_index("ix_duplicate_groups_kind", "duplicate_groups", ["kind"])
    op.create_index("ix_duplicate_groups_status", "duplicate_groups", ["status"])

    op.create_table(
        "duplicate_group_members",
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("duplicate_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "photo_id",
            sa.Integer(),
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("similarity_pct", sa.Integer(), nullable=False),
    )
    op.create_index("ix_duplicate_group_members_photo_id", "duplicate_group_members", ["photo_id"])

    op.create_table(
        "duplicate_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("duplicate_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "photo_id",
            sa.Integer(),
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("group_id", "photo_id"),
    )
    op.create_index("ix_duplicate_decisions_group_id", "duplicate_decisions", ["group_id"])


def downgrade() -> None:
    op.drop_table("duplicate_decisions")
    op.drop_table("duplicate_group_members")
    op.drop_table("duplicate_groups")
