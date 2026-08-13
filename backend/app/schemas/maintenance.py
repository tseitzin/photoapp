from pydantic import BaseModel, Field


class BackfillGpsRequest(BaseModel):
    # Cursor from the previous response; 0 starts from the beginning.
    after_id: int = Field(default=0, ge=0)
    # Deliberately small. Each candidate costs an EXIF header read from wherever
    # the library lives, and a chunk of 1,000 measured 13.4s in one request —
    # long enough to risk a client timeout, and long enough that the progress
    # bar sat still and Stop took 13s to be noticed. The caller already loops on
    # a cursor, so a smaller bite costs only round trips.
    limit: int = Field(default=200, ge=1, le=5000)


class BackfillResultRead(BaseModel):
    processed: int
    updated: int
    # Pass back as after_id to continue; null means the sweep is done.
    next_after_id: int | None
    remaining: int
