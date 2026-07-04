from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.scan_roots import ScanRootRepository
from app.schemas.scan_roots import ScanRootCreate, ScanRootRead, ScanRootUpdate
from app.services.scan_roots import ScanRootService

router = APIRouter(prefix="/scan-roots")


def get_service(db: Annotated[Session, Depends(get_db)]) -> ScanRootService:
    return ScanRootService(ScanRootRepository(db))


Service = Annotated[ScanRootService, Depends(get_service)]


@router.get("")
def list_scan_roots(service: Service) -> list[ScanRootRead]:
    return [ScanRootRead.model_validate(root) for root in service.list_roots()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_scan_root(body: ScanRootCreate, service: Service) -> ScanRootRead:
    return ScanRootRead.model_validate(service.add_root(body.path))


@router.patch("/{root_id}")
def update_scan_root(root_id: int, body: ScanRootUpdate, service: Service) -> ScanRootRead:
    return ScanRootRead.model_validate(service.set_enabled(root_id, body.enabled))


@router.delete("/{root_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scan_root(root_id: int, service: Service) -> None:
    service.remove_root(root_id)
