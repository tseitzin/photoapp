from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

PhotoStatus = Literal["active", "missing", "quarantined"]


class PhotoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    root_id: int
    path: str
    filename: str
    ext: str
    mime: str
    size_bytes: int
    width: int | None
    height: int | None
    captured_at: datetime | None
    camera_make: str | None
    camera_model: str | None
    status: PhotoStatus
    created_at: datetime


class PhotoDetail(PhotoRead):
    sha256: str | None
    mtime_ns: int
    exif: dict[str, Any] | None
    last_error: str | None
    updated_at: datetime


class PhotoPage(BaseModel):
    items: list[PhotoRead]
    total: int
    limit: int
    offset: int
