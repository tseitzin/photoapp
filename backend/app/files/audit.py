"""Append-only audit-log writer shared by every file-moving operation."""

from sqlalchemy.orm import Session

from app.models import FileOperation


def record_operation(
    session: Session,
    photo_id: int,
    op: str,
    src: str,
    dest: str | None,
    batch_id: str,
    size_bytes: int,
) -> None:
    session.add(
        FileOperation(
            photo_id=photo_id,
            op=op,
            src_path=src,
            dest_path=dest,
            batch_id=batch_id,
            size_bytes=size_bytes,
        )
    )
