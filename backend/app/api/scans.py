from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db, get_session_factory
from app.jobs.runner import JobRunner, get_job_runner
from app.schemas.scans import ScanCreate, ScanErrorPage, ScanErrorRead, ScanRead
from app.services.scans import ScanService

router = APIRouter(prefix="/scans")


def get_service(
    db: Annotated[Session, Depends(get_db)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> ScanService:
    return ScanService(db, runner, session_factory)


Service = Annotated[ScanService, Depends(get_service)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_scan(body: ScanCreate, service: Service) -> ScanRead:
    return ScanRead.model_validate(service.start(body.root_ids))


@router.get("")
def list_scans(service: Service, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[ScanRead]:
    return [ScanRead.model_validate(scan) for scan in service.list_recent(limit)]


@router.get("/{scan_id}")
def get_scan(scan_id: int, service: Service) -> ScanRead:
    return ScanRead.model_validate(service.get(scan_id))


@router.post("/{scan_id}/cancel")
def cancel_scan(scan_id: int, service: Service) -> ScanRead:
    return ScanRead.model_validate(service.cancel(scan_id))


@router.get("/{scan_id}/errors")
def list_scan_errors(
    scan_id: int,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScanErrorPage:
    items, total = service.errors(scan_id, limit=limit, offset=offset)
    return ScanErrorPage(
        items=[ScanErrorRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
