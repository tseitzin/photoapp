from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SCAN_STATUSES = ("pending", "running", "completed", "failed", "cancelled")
ACTIVE_SCAN_STATUSES = ("pending", "running")


class Scan(Base):
    """Persisted job state — what makes scans pollable and resumable."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(
        String(12), default="pending", server_default="pending", index=True
    )
    # None = all enabled roots at execution time.
    root_ids: Mapped[list[int] | None] = mapped_column(JSONB)
    files_found: Mapped[int] = mapped_column(default=0, server_default="0")
    files_processed: Mapped[int] = mapped_column(default=0, server_default="0")
    files_added: Mapped[int] = mapped_column(default=0, server_default="0")
    files_changed: Mapped[int] = mapped_column(default=0, server_default="0")
    files_unchanged: Mapped[int] = mapped_column(default=0, server_default="0")
    files_missing: Mapped[int] = mapped_column(default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(default=0, server_default="0")
    current_path: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanError(Base):
    __tablename__ = "scan_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    error: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
