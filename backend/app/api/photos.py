from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Photo
from app.repositories.photos import PhotoRepository
from app.scanner.thumbnails import ensure_thumbnail
from app.schemas.photos import PhotoDetail, PhotoPage, PhotoRead, PhotoStatus
from app.services.errors import NotFoundError

router = APIRouter(prefix="/photos")

# sha256-addressed content: safe to cache forever.
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


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


def _serve_image(photo: Photo | None, photo_id: int, size: int) -> FileResponse:
    """Serve a cached rendition by photo id — raw paths are never exposed."""
    if photo is None:
        raise NotFoundError(f"Photo {photo_id} not found")
    if photo.sha256 is None:
        raise NotFoundError(f"Photo {photo_id} has no readable content")
    settings = get_settings()
    path = ensure_thumbnail(photo.path, photo.sha256, settings.thumbnail_cache_dir, size)
    if path is None:
        raise NotFoundError(f"No preview available for photo {photo_id}")
    return FileResponse(path, media_type="image/webp", headers=_IMMUTABLE)


@router.get("/{photo_id}/thumbnail")
def get_thumbnail(photo_id: int, repository: Repository) -> FileResponse:
    return _serve_image(repository.get(photo_id), photo_id, get_settings().thumbnail_size)


@router.get("/{photo_id}/preview")
def get_preview(photo_id: int, repository: Repository) -> FileResponse:
    return _serve_image(repository.get(photo_id), photo_id, get_settings().preview_size)
