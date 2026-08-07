"""Store each photo's directory, so folder queries stop scanning the table.

Two of the Library's queries derived the directory with
`regexp_replace(path, '/[^/]*$', '')` evaluated per row: the folder count in
`GET /api/stats` and the folder tree in `GET /api/folders`. A function call on
every row cannot use an index, so both were sequential scans over the whole
`photos` heap — which carries the ~1.3 KB `exif` blob on every row it reads.

A stored generated column moves that work to write time, and an index on
(status, directory) makes both queries index-only: they no longer touch the heap
at all, so the width of `exif` stops mattering to them.

Measured on 100k rows over 2,000 folders:

    folder count   169.7 ms / 16,670 buffers  ->  6.5 ms / 93 buffers
    folder tree     88.9 ms / 16,704 buffers  ->  9.1 ms / 93 buffers

`directory` is derived from `path` by the database, so it cannot drift: an
organize move updates path and Postgres recomputes the rest.

Adding a STORED generated column rewrites the table and takes an ACCESS
EXCLUSIVE lock. This is a single-user local app whose whole library is thousands
of rows, so the rewrite is seconds and nothing is serving traffic meanwhile.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-06

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Raw SQL: op.add_column() cannot express a generated column.
_ADD_COLUMN = (
    "ALTER TABLE photos ADD COLUMN directory text "
    "GENERATED ALWAYS AS (regexp_replace(path, '/[^/]*$', '')) STORED"
)
# Leads with status to match every other list index, and because both callers
# filter on it. The trailing directory column is what makes the scan index-only.
_INDEX = "CREATE INDEX IF NOT EXISTS ix_photos_status_directory ON photos (status, directory)"


def upgrade() -> None:
    op.execute(_ADD_COLUMN)
    op.execute(_INDEX)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_photos_status_directory")
    op.execute("ALTER TABLE photos DROP COLUMN IF EXISTS directory")
