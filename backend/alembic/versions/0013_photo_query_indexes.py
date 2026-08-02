"""Indexes for the Library's real filter+sort combinations.

Before this, `photos` was indexed on root_id, sha256, status,
marked_for_deletion and the eight pHash bands — and on nothing the Library
actually queries by. Every page load was two sequential scans (one for the
COUNT, one for the page) plus a sort; at 4.5k rows that is ~12 ms and
invisible, but the table is ~180 MB at 50k and the sort already spills to disk
at deep offsets.

Each composite leads with `status` (every list query filters status='active')
and ends with `id` (the tiebreaker every sort in _SORTS already applies), so
the planner can walk the index in output order instead of sorting.

Index-only additions plus two swaps that reduce write cost during scans; no
data is read, written, or moved.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-02

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, DDL body). Raw SQL because these need DESC/NULLS LAST ordering and
# opclasses, which op.create_index() cannot express.
_INDEXES: tuple[tuple[str, str], ...] = (
    # sort=captured_desc — the Library default.
    (
        "ix_photos_status_captured_desc",
        "photos (status, captured_at DESC NULLS LAST, id DESC)",
    ),
    # sort=captured_asc. A backward scan of the index above cannot serve this:
    # reversing DESC NULLS LAST yields ASC NULLS FIRST, not ASC NULLS LAST.
    (
        "ix_photos_status_captured_asc",
        "photos (status, captured_at ASC NULLS LAST, id ASC)",
    ),
    # sort=name_asc, and name_desc via a backward scan (filename is NOT NULL,
    # so there is no NULLS-position mismatch).
    ("ix_photos_status_filename", "photos (status, filename, id)"),
    # sort=size_asc / size_desc, same reasoning.
    ("ix_photos_status_size", "photos (status, size_bytes, id)"),
    # Folder filter: Photo.path.like('<dir>/%'). The unique index on path is
    # built with the database's en_US.utf8 collation and cannot serve a prefix
    # LIKE; text_pattern_ops can.
    ("ix_photos_path_prefix", "photos (path text_pattern_ops)"),
    # Filename search: ILIKE '%q%'. A leading wildcard rules out any b-tree.
    ("ix_photos_filename_trgm", "photos USING gin (filename gin_trgm_ops)"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, body in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {body}")

    # Redundant now that every list index leads with status, and useless for
    # selectivity regardless — essentially every row is 'active'.
    op.execute("DROP INDEX IF EXISTS ix_photos_status")
    # A plain b-tree over a boolean that is false for nearly every row indexes
    # the whole table; the partial index holds only the flagged rows.
    op.execute("DROP INDEX IF EXISTS ix_photos_marked_for_deletion")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_photos_marked_for_deletion "
        "ON photos (marked_for_deletion) WHERE marked_for_deletion"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_photos_marked_for_deletion")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_photos_marked_for_deletion ON photos (marked_for_deletion)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_photos_status ON photos (status)")
    for name, _ in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    # pg_trgm is left installed: dropping an extension another migration or a
    # future feature may rely on is not worth the churn.
