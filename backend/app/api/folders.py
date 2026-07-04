from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.photos import FolderNodeRead
from app.services.folders import build_folder_tree

router = APIRouter(prefix="/folders")


@router.get("")
def list_folders(db: Annotated[Session, Depends(get_db)]) -> list[FolderNodeRead]:
    return [FolderNodeRead.model_validate(node) for node in build_folder_tree(db)]
