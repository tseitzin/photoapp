"""Finish making /api/stats index-only, and keep the visibility map fresh.

Two things, both about the same effect: an index-only scan is only index-only
when the visibility map says the pages are all-visible. Otherwise Postgres falls
back to the heap and the index buys nothing.

**The stats aggregate.** The duplicate preview groups active photos by sha256 and
sums size_bytes. `ix_photos_sha256` covers neither status nor size_bytes, so the
query read the whole heap. Widening it to (status, sha256, size_bytes) makes that
scan index-only, and still serves every sha256 lookup in the codebase — all of
them filter status='active' alongside it, so the leading column costs nothing.
A swap rather than an addition: `photos` already carries twenty indexes, and each
one is written on every insert during an import.

**Autovacuum.** Measured before this migration, `SELECT count(*) WHERE
status='active'` planned as a sequential scan over 1,024 buffers (7.07 ms). After
a plain VACUUM it planned as an index-only scan over 8 buffers with zero heap
fetches — 0.41 ms, 17x quicker — purely because the visibility map had caught up.

The defaults do not suit this table. Autovacuum triggers on updates and deletes,
so an import that only *inserts* leaves the map stale until the insert threshold
is reached, which by default is 20% of the table. The lowered scale factors below
mean a large import is followed by a vacuum while the pages are still warm,
rather than leaving the next stats query to read the heap.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-06

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUTOVACUUM = (
    # Vacuum after 5% churn rather than 20%, so the visibility map stays useful.
    "autovacuum_vacuum_scale_factor = 0.05, "
    # Insert-only work is what an import is, and it has its own threshold.
    "autovacuum_vacuum_insert_scale_factor = 0.05, "
    # Statistics matter as much: the planner only picks the index-only scan when
    # it believes the row counts.
    "autovacuum_analyze_scale_factor = 0.02"
)


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_photos_status_sha256_size "
        "ON photos (status, sha256, size_bytes)"
    )
    op.execute("DROP INDEX IF EXISTS ix_photos_sha256")
    op.execute(f"ALTER TABLE photos SET ({_AUTOVACUUM})")

    # Outside the migration's transaction: VACUUM cannot run inside one. This is
    # the one-time catch-up that makes the settings above the steady state
    # rather than something that only takes effect after the next big import.
    with op.get_context().autocommit_block():
        op.execute("VACUUM (ANALYZE) photos")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE photos RESET (autovacuum_vacuum_scale_factor, "
        "autovacuum_vacuum_insert_scale_factor, autovacuum_analyze_scale_factor)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_photos_sha256 ON photos (sha256)")
    op.execute("DROP INDEX IF EXISTS ix_photos_status_sha256_size")
