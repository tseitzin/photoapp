from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QuarantineRequest(BaseModel):
    photo_ids: list[int] = Field(min_length=1)
    # Required to quarantine every remaining active member of a duplicate group.
    force: bool = False


class RestoreRequest(BaseModel):
    photo_ids: list[int] = Field(min_length=1)


class DeleteRequest(BaseModel):
    photo_ids: list[int] = Field(min_length=1)
    # Must be explicitly true; permanent deletion cannot be undone.
    confirm: bool = False


class ItemResultRead(BaseModel):
    photo_id: int
    ok: bool
    error: str | None = None


class BatchResultRead(BaseModel):
    batch_id: str
    succeeded: int
    failed: int
    results: list[ItemResultRead]


class FileOperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int | None
    op: Literal["quarantine", "restore", "delete"]
    src_path: str
    dest_path: str | None
    batch_id: str
    performed_at: datetime


class FileOperationPage(BaseModel):
    items: list[FileOperationRead]
    total: int
    limit: int
    offset: int
