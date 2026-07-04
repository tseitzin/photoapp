from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.photos import PhotoRepository
from app.schemas.photos import PhotoDetail, PhotoPage, PhotoRead, PhotoStatus
from app.services.errors import NotFoundError

router = APIRouter(prefix="/photos")


def get_repository(db: Annotated[Session, Depends(get_db)]) -> PhotoRepository:
    return PhotoRepository(db)


Repository = Annotated[PhotoRepository, Depends(get_repository)]


@router.get("")
def list_photos(
    repository: Repository,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: PhotoStatus | None = None,
) -> PhotoPage:
    items, total = repository.list_page(limit=limit, offset=offset, status=status)
    return PhotoPage(
        items=[PhotoRead.model_validate(photo) for photo in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{photo_id}")
def get_photo(photo_id: int, repository: Repository) -> PhotoDetail:
    photo = repository.get(photo_id)
    if photo is None:
        raise NotFoundError(f"Photo {photo_id} not found")
    return PhotoDetail.model_validate(photo)
