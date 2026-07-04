from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import DuplicateDecision, Photo
from app.repositories.duplicates import DuplicateRepository
from app.schemas.duplicates import (
    DecisionsWrite,
    DuplicateGroupPage,
    DuplicateGroupRead,
    DuplicateKind,
    DuplicateSummary,
    GroupStatus,
    RebuildRead,
)
from app.schemas.photos import PhotoRead
from app.services.duplicates import DuplicateService, rebuild_duplicate_groups

router = APIRouter(prefix="/duplicates")


def get_service(db: Annotated[Session, Depends(get_db)]) -> DuplicateService:
    return DuplicateService(db)


Service = Annotated[DuplicateService, Depends(get_service)]


@router.get("/groups")
def list_groups(
    service: Service,
    kind: DuplicateKind | None = None,
    status: GroupStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DuplicateGroupPage:
    groups, total = service.list_groups(kind=kind, status=status, limit=limit, offset=offset)
    return DuplicateGroupPage(
        items=[DuplicateGroupRead.from_group(group) for group in groups],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/groups/{group_id}")
def get_group(group_id: int, service: Service) -> DuplicateGroupRead:
    return DuplicateGroupRead.from_group(service.get_group(group_id))


@router.post("/groups/{group_id}/decisions")
def decide(group_id: int, body: DecisionsWrite, service: Service) -> DuplicateGroupRead:
    group = service.decide(group_id, [(d.photo_id, d.decision) for d in body.decisions])
    return DuplicateGroupRead.from_group(group)


@router.post("/groups/{group_id}/dismiss")
def dismiss(group_id: int, service: Service) -> DuplicateGroupRead:
    return DuplicateGroupRead.from_group(service.dismiss(group_id))


@router.get("/marked")
def list_marked_for_removal(db: Annotated[Session, Depends(get_db)]) -> list[PhotoRead]:
    """Active photos the user has marked 'remove' — the quarantine work-list."""
    photos = db.scalars(
        select(Photo)
        .join(DuplicateDecision, DuplicateDecision.photo_id == Photo.id)
        .where(DuplicateDecision.decision == "remove", Photo.status == "active")
        .distinct()
        .order_by(Photo.path)
    ).all()
    return [PhotoRead.model_validate(photo) for photo in photos]


@router.get("/summary")
def summary(db: Annotated[Session, Depends(get_db)]) -> DuplicateSummary:
    return DuplicateSummary(**DuplicateRepository(db).summary())


@router.post("/rebuild")
def rebuild(db: Annotated[Session, Depends(get_db)]) -> RebuildRead:
    result = rebuild_duplicate_groups(db)
    return RebuildRead(exact_groups=result.exact_groups, similar_groups=result.similar_groups)
