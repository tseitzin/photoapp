from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OrganizeMode = Literal["keep", "date", "camera"]
OrganizeStatus = Literal["pending", "running", "completed", "failed"]


class OrganizeRequest(BaseModel):
    folders: list[str] = Field(min_length=1)
    destination: str = Field(min_length=1)
    mode: OrganizeMode
    rename: bool = False
    skip_duplicates: bool = True


class RenameExample(BaseModel):
    old: str
    new: str


class OrganizePreviewRead(BaseModel):
    total: int
    planned: int
    duplicates_in_set: int
    duplicates_skipped: int
    already_organized: int
    undated: int
    est_bytes: int
    # First few planned destinations, one per distinct target directory.
    example_paths: list[str]
    rename_example: RenameExample | None


class OrganizeRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrganizeStatus
    params: OrganizeRequest
    batch_id: str
    total: int
    planned: int
    moved: int
    skipped_duplicates: int
    already_organized: int
    undated: int
    failed_count: int
    est_bytes: int
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
