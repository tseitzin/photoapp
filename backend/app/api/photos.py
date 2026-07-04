from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.dedupe.similarity import similarity_pct
from app.models import Photo
from app.repositories.photos import PhotoRepository, expand_ext_filter
from app.scanner.thumbnails import ensure_thumbnail
from app.schemas.photos import (
    FacetsRead,
    FacetValue,
    PhotoDetail,
    PhotoPage,
    PhotoRead,
    PhotoSort,
    PhotoStatus,
    SimilarPhotoRead,
)
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
    folder: Annotated[str | None, Query(description="Directory path; recursive")] = None,
    type: Annotated[list[str] | None, Query()] = None,  # noqa: A002 - API name
    camera: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: PhotoSort = "captured_desc",
) -> PhotoPage:
    items, total = repository.list_page(
        limit=limit,
        offset=offset,
        status=status,
        folder=folder,
        exts=expand_ext_filter(type) if type else None,
        cameras=camera,
        q=q,
        sort=sort,
    )
    return PhotoPage(
        items=[PhotoRead.model_validate(photo) for photo in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/facets")
def get_facets(repository: Repository) -> FacetsRead:
    type_counts, camera_counts = repository.facets()
    return FacetsRead(
        file_types=[
            FacetValue(value=value, count=count)
            for value, count in sorted(type_counts.items(), key=lambda kv: -kv[1])
        ],
        cameras=[FacetValue(value=value, count=count) for value, count in camera_counts.items()],
    )


@router.get("/{photo_id}")
def get_photo(photo_id: int, repository: Repository) -> PhotoDetail:
    photo = repository.get(photo_id)
    if photo is None:
        raise NotFoundError(f"Photo {photo_id} not found")
    return PhotoDetail.model_validate(photo)


@router.get("/{photo_id}/similar")
def get_similar(
    photo_id: int,
    repository: Repository,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> list[SimilarPhotoRead]:
    photo = repository.get(photo_id)
    if photo is None:
        raise NotFoundError(f"Photo {photo_id} not found")
    threshold = get_settings().similar_hamming_threshold
    return [
        SimilarPhotoRead(
            photo=PhotoRead.model_validate(match),
            distance=distance,
            similarity_pct=similarity_pct(distance),
        )
        for match, distance in repository.similar_to(photo, threshold=threshold, limit=limit)
    ]


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
