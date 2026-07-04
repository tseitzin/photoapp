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


PhotoSort = Literal[
    "captured_desc",
    "captured_asc",
    "name_asc",
    "name_desc",
    "size_desc",
    "size_asc",
    "added_desc",
]


class FacetValue(BaseModel):
    value: str
    count: int


class FacetsRead(BaseModel):
    file_types: list[FacetValue]
    cameras: list[FacetValue]


class SimilarPhotoRead(BaseModel):
    photo: PhotoRead
    distance: int
    similarity_pct: int


class FolderNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path: str
    name: str
    parent_path: str | None
    depth: int
    photo_count: int
    direct_count: int
    has_children: bool
    root_id: int
