"""Record file size on audit-log operations.

Lets lifetime tallies (photos deleted, disk space reclaimed) be computed from
the append-only file_operations log, which survives after photo rows are gone.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("file_operations", sa.Column("size_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("file_operations", "size_bytes")
