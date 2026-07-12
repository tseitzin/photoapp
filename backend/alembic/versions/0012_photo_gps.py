"""GPS coordinates on photos.

Decimal-degree latitude/longitude extracted from the EXIF GPS IFD during
scans (groundwork for a future group-by-location feature). Existing photos
backfill via POST /api/maintenance/backfill-gps.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("latitude", sa.Float(precision=53), nullable=True))
    op.add_column("photos", sa.Column("longitude", sa.Float(precision=53), nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "longitude")
    op.drop_column("photos", "latitude")
