from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScanRootCreate(BaseModel):
    path: str = Field(min_length=1, description="Absolute path of a directory to index")


class ScanRootUpdate(BaseModel):
    enabled: bool


class ScanRootRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    enabled: bool
    created_at: datetime
