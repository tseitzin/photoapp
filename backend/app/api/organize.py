from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db, get_session_factory
from app.files.organize import OrganizePlan, OrganizeSpec, PlannedMove
from app.jobs.runner import JobRunner, get_job_runner
from app.schemas.organize import (
    OrganizePreviewRead,
    OrganizeRequest,
    OrganizeRunRead,
    RenameExample,
)
from app.services.organize import OrganizeService

router = APIRouter(prefix="/organize")


def get_service(
    db: Annotated[Session, Depends(get_db)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> OrganizeService:
    return OrganizeService(db, runner, session_factory)


Service = Annotated[OrganizeService, Depends(get_service)]


def _spec(body: OrganizeRequest) -> OrganizeSpec:
    return OrganizeSpec.from_params(body.model_dump())


def _example_paths(moves: list[PlannedMove], limit: int = 3) -> list[str]:
    """One example per distinct target directory, in plan order."""
    seen_dirs: set[str] = set()
    examples: list[str] = []
    for move in moves:
        parent = str(Path(move.dest).parent)
        if parent in seen_dirs:
            continue
        seen_dirs.add(parent)
        examples.append(move.dest)
        if len(examples) == limit:
            break
    return examples


def _preview_read(plan: OrganizePlan) -> OrganizePreviewRead:
    rename_example = None
    if plan.rename_example is not None:
        rename_example = RenameExample(old=plan.rename_example[0], new=plan.rename_example[1])
    return OrganizePreviewRead(
        total=plan.total,
        planned=len(plan.moves),
        duplicates_in_set=plan.duplicates_in_set,
        duplicates_skipped=plan.duplicates_skipped,
        already_organized=plan.already_organized,
        undated=plan.undated,
        est_bytes=plan.est_bytes,
        example_paths=_example_paths(plan.moves),
        rename_example=rename_example,
        destination_new_root=plan.destination_new_root,
        destination_inside_source=plan.destination_inside_source,
    )


@router.post("/preview")
def preview_organize(body: OrganizeRequest, service: Service) -> OrganizePreviewRead:
    return _preview_read(service.preview(_spec(body)))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_organize(body: OrganizeRequest, service: Service) -> OrganizeRunRead:
    return OrganizeRunRead.model_validate(service.start(_spec(body)))


@router.get("")
def list_organize_runs(
    service: Service, limit: Annotated[int, Query(ge=1, le=100)] = 5
) -> list[OrganizeRunRead]:
    return [OrganizeRunRead.model_validate(run) for run in service.list_recent(limit)]


@router.get("/{run_id}")
def get_organize_run(run_id: int, service: Service) -> OrganizeRunRead:
    return OrganizeRunRead.model_validate(service.get(run_id))
