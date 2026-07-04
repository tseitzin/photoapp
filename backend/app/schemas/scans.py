from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ScanStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class ScanCreate(BaseModel):
    # None = scan all enabled roots.
    root_ids: list[int] | None = None


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ScanStatus
    root_ids: list[int] | None
    files_found: int
    files_processed: int
    files_added: int
    files_changed: int
    files_unchanged: int
    files_missing: int
    files_moved: int
    error_count: int
    current_path: str | None
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ScanErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    error: str
    created_at: datetime


class ScanErrorPage(BaseModel):
    items: list[ScanErrorRead]
    total: int
    limit: int
    offset: int
