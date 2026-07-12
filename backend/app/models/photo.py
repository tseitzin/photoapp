from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    false,
    func,
)
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
    # GPS coordinates in decimal degrees (double precision — REAL truncates).
    latitude: Mapped[float | None] = mapped_column(Float(53))
    longitude: Mapped[float | None] = mapped_column(Float(53))
    exif: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    # 64-bit perceptual hash stored signed; the 8 generated band columns below
    # implement LSH candidate lookup: any two hashes within Hamming distance 7
    # agree exactly on at least one byte-band (pigeonhole), so an indexed
    # equality check per band finds every candidate pair.
    phash: Mapped[int | None] = mapped_column(BigInteger)
    phash_b0: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 0) & 255)::smallint", persisted=True), index=True
    )
    phash_b1: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 8) & 255)::smallint", persisted=True), index=True
    )
    phash_b2: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 16) & 255)::smallint", persisted=True), index=True
    )
    phash_b3: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 24) & 255)::smallint", persisted=True), index=True
    )
    phash_b4: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 32) & 255)::smallint", persisted=True), index=True
    )
    phash_b5: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 40) & 255)::smallint", persisted=True), index=True
    )
    phash_b6: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 48) & 255)::smallint", persisted=True), index=True
    )
    phash_b7: Mapped[int | None] = mapped_column(
        SmallInteger, Computed("((phash >> 56) & 255)::smallint", persisted=True), index=True
    )
    status: Mapped[str] = mapped_column(
        String(12), default="active", server_default="active", index=True
    )
    # User-flagged from the Library for deletion; a soft mark (no file movement)
    # that feeds the quarantine work-list. Cleared when the photo is quarantined.
    marked_for_deletion: Mapped[bool] = mapped_column(
        default=False, server_default=false(), index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
