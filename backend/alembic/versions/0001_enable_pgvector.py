"""Enable the pgvector extension.

Costs nothing now; keeps the future image-embeddings path (photo_embeddings
table with a vector column) open without a disruptive migration later.

Revision ID: 0001
Revises:
Create Date: 2026-07-03

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
