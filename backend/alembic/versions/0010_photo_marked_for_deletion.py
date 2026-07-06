"""Add marked_for_deletion flag to photos.

Lets the user flag photos from the Library for deletion (a soft mark that feeds
the quarantine work-list) without moving any files.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column(
            "marked_for_deletion",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_photos_marked_for_deletion", "photos", ["marked_for_deletion"])


def downgrade() -> None:
    op.drop_index("ix_photos_marked_for_deletion", table_name="photos")
    op.drop_column("photos", "marked_for_deletion")
