from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ORGANIZE_STATUSES = ("pending", "running", "completed", "failed")
ACTIVE_ORGANIZE_STATUSES = ("pending", "running")


class OrganizeRun(Base):
    """Persisted job state for a physical organize — pollable like a Scan.

    `params` holds the submitted OrganizeSpec verbatim so the job re-derives its
    plan from the database at execution time; `batch_id` ties every move to its
    file_operations audit rows.
    """

    __tablename__ = "organize_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(
        String(12), default="pending", server_default="pending", index=True
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    batch_id: Mapped[str] = mapped_column(String(36))
    total: Mapped[int] = mapped_column(default=0, server_default="0")
    planned: Mapped[int] = mapped_column(default=0, server_default="0")
    moved: Mapped[int] = mapped_column(default=0, server_default="0")
    skipped_duplicates: Mapped[int] = mapped_column(default=0, server_default="0")
    already_organized: Mapped[int] = mapped_column(default=0, server_default="0")
    undated: Mapped[int] = mapped_column(default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(default=0, server_default="0")
    est_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
