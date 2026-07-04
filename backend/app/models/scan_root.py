from datetime import datetime

from sqlalchemy import DateTime, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScanRoot(Base):
    """A directory the user has approved for indexing. Paths are stored resolved."""

    __tablename__ = "scan_roots"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(Text, unique=True)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
