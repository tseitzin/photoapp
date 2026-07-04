from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Lifecycle: active -> missing (not seen by a scan) -> active again if it
# reappears; quarantined via the Phase 6 file-management workflow.
PHOTO_STATUSES = ("active", "missing", "quarantined")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    root_id: Mapped[int] = mapped_column(
        ForeignKey("scan_roots.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text, unique=True)
    filename: Mapped[str] = mapped_column(Text)
    ext: Mapped[str] = mapped_column(String(10))
    mime: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mtime_ns: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None]
    height: Mapped[int | None]
    # EXIF timestamps carry no timezone — stored naive on purpose.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime())
    camera_make: Mapped[str | None] = mapped_column(Text)
    camera_model: Mapped[str | None] = mapped_column(Text)
    exif: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    # 64-bit perceptual hash stored signed; LSH band columns arrive in Phase 5.
    phash: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(12), default="active", server_default="active", index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
