"""File-operations audit log.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "file_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "photo_id",
            sa.Integer(),
            sa.ForeignKey("photos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("op", sa.String(length=12), nullable=False),
        sa.Column("src_path", sa.Text(), nullable=False),
        sa.Column("dest_path", sa.Text(), nullable=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_file_operations_photo_id", "file_operations", ["photo_id"])
    op.create_index("ix_file_operations_op", "file_operations", ["op"])
    op.create_index("ix_file_operations_batch_id", "file_operations", ["batch_id"])


def downgrade() -> None:
    op.drop_table("file_operations")
