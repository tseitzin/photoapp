"""Nearest-place name for photos that have coordinates.

Derived from photos.latitude/longitude by offline reverse geocoding (see
app/geo/places.py) during scans, and backfilled for existing photos by
POST /api/maintenance/backfill-gps.

Stored rather than computed per request: the lookup tree costs ~100 MB
resident, and these columns are what a future group-by-location would filter
on. `place_distance_km` is kept so the UI can say "near Gorham" when the
nearest known town is some way off, instead of claiming the photo was taken
there.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("region", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("country", sa.String(length=2), nullable=True))
    op.add_column("photos", sa.Column("place_distance_km", sa.Float(precision=24), nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "place_distance_km")
    op.drop_column("photos", "country")
    op.drop_column("photos", "region")
    op.drop_column("photos", "city")
