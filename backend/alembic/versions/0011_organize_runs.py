"""Organize-run job state.

Persisted state for physical organize jobs (move photos into a chosen folder
structure), pollable by the UI like scans.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organize_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("moved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("already_organized", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("undated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("est_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_organize_runs_status", "organize_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_organize_runs_status", table_name="organize_runs")
    op.drop_table("organize_runs")
