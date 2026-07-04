from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

FILE_OPS = ("quarantine", "restore", "delete")


class FileOperation(Base):
    """Append-only audit log of every file the app has moved or deleted.

    photo_id is SET NULL if the photo row ever goes away — the audit row and
    its paths survive regardless.
    """

    __tablename__ = "file_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int | None] = mapped_column(
        ForeignKey("photos.id", ondelete="SET NULL"), index=True
    )
    op: Mapped[str] = mapped_column(String(12), index=True)
    src_path: Mapped[str] = mapped_column(Text)
    dest_path: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
