from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.files.quarantine import BatchResult, FileManagementService
from app.models import FileOperation
from app.schemas.files import (
    BatchResultRead,
    DeleteRequest,
    FileOperationPage,
    FileOperationRead,
    ItemResultRead,
    QuarantineRequest,
    RestoreRequest,
)

router = APIRouter()


def get_service(db: Annotated[Session, Depends(get_db)]) -> FileManagementService:
    return FileManagementService(db)


Service = Annotated[FileManagementService, Depends(get_service)]


def _to_read(result: BatchResult) -> BatchResultRead:
    return BatchResultRead(
        batch_id=result.batch_id,
        succeeded=result.succeeded,
        failed=len(result.results) - result.succeeded,
        results=[
            ItemResultRead(photo_id=r.photo_id, ok=r.ok, error=r.error) for r in result.results
        ],
    )


@router.post("/quarantine")
def quarantine(body: QuarantineRequest, service: Service) -> BatchResultRead:
    return _to_read(service.quarantine(body.photo_ids, force=body.force))


@router.post("/quarantine/restore")
def restore(body: RestoreRequest, service: Service) -> BatchResultRead:
    return _to_read(service.restore(body.photo_ids))


@router.post("/quarantine/delete")
def delete_permanently(body: DeleteRequest, service: Service) -> BatchResultRead:
    return _to_read(service.delete_permanently(body.photo_ids, confirm=body.confirm))


@router.get("/file-operations")
def list_file_operations(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FileOperationPage:
    total = db.scalar(select(func.count()).select_from(FileOperation)) or 0
    items = db.scalars(
        select(FileOperation).order_by(FileOperation.id.desc()).limit(limit).offset(offset)
    ).all()
    return FileOperationPage(
        items=[FileOperationRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
