from pydantic import BaseModel, Field


class BackfillGpsRequest(BaseModel):
    # Cursor from the previous response; 0 starts from the beginning.
    after_id: int = Field(default=0, ge=0)
    limit: int = Field(default=1000, ge=1, le=5000)


class BackfillResultRead(BaseModel):
    processed: int
    updated: int
    # Pass back as after_id to continue; null means the sweep is done.
    next_after_id: int | None
    remaining: int
