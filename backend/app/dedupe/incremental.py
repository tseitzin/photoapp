"""Incremental duplicate-group maintenance for file operations.

Quarantine/restore/delete change only a handful of photos' active status. Instead
of re-deriving every group over the whole library (`rebuild_duplicate_groups`, a
scan-weight op that is O(n) + O(k^2)-per-band and does not scale to 70k+), update
only the groups the affected photos touch — O(affected).

- Removal (quarantine/delete): drop the photos' memberships and delete any group
  left with < 2 active members.
- Restore: re-form EXACT groups for the restored photos (the common case — a
  cheap sha256 index lookup). Similar-group membership for a restored photo is
  left to the next scan's full rebuild (rare path, avoids component-merge edge
  cases).
"""

import logging
from collections.abc import Collection

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DuplicateGroup, DuplicateGroupMember, Photo

logger = logging.getLogger(__name__)


def _keeper_id(photos: list[Photo]) -> int:
    """Highest resolution, then largest file, then oldest row — matches keeper_of."""
    return max(photos, key=lambda p: ((p.width or 0) * (p.height or 0), p.size_bytes, -p.id)).id


def remove_photos_from_groups(session: Session, photo_ids: Collection[int]) -> None:
    """Prune photos leaving the active set (quarantine/delete) from their groups,
    deleting any group left with fewer than 2 active members."""
    ids = list(photo_ids)
    if not ids:
        return
    affected = set(
        session.scalars(
            select(DuplicateGroupMember.group_id).where(DuplicateGroupMember.photo_id.in_(ids))
        ).all()
    )
    if not affected:
        return
    session.execute(delete(DuplicateGroupMember).where(DuplicateGroupMember.photo_id.in_(ids)))
    session.flush()
    for group_id in affected:
        _reconcile_after_removal(session, group_id)
    session.commit()
    logger.info("pruned %d photo(s) from %d group(s)", len(ids), len(affected))


def _reconcile_after_removal(session: Session, group_id: int) -> None:
    group = session.get(DuplicateGroup, group_id)
    if group is None:
        return
    remaining = session.scalars(
        select(Photo)
        .join(DuplicateGroupMember, DuplicateGroupMember.photo_id == Photo.id)
        .where(DuplicateGroupMember.group_id == group_id, Photo.status == "active")
    ).all()
    if len(remaining) < 2:
        session.delete(group)  # cascades members + decisions
        return
    if group.keeper_photo_id not in {p.id for p in remaining}:
        group.keeper_photo_id = _keeper_id(list(remaining))


def add_photos_to_groups(session: Session, photo_ids: Collection[int]) -> None:
    """Re-form exact duplicate groups for photos re-entering the active set
    (restore). Similar-group membership is reconciled by the next scan."""
    ids = list(photo_ids)
    if not ids:
        return
    for pid in ids:
        photo = session.get(Photo, pid)
        if photo is None or photo.status != "active" or photo.sha256 is None:
            continue
        copies = session.scalars(
            select(Photo).where(Photo.sha256 == photo.sha256, Photo.status == "active")
        ).all()
        if len(copies) < 2:
            continue
        _upsert_exact_group(session, photo.sha256, list(copies))
    session.commit()


def _upsert_exact_group(session: Session, sha256: str, copies: list[Photo]) -> None:
    group = session.scalar(
        select(DuplicateGroup).where(DuplicateGroup.kind == "exact", DuplicateGroup.key == sha256)
    )
    keeper = _keeper_id(copies)
    if group is None:
        group = DuplicateGroup(kind="exact", key=sha256, keeper_photo_id=keeper)
        group.members = [DuplicateGroupMember(photo_id=p.id, similarity_pct=100) for p in copies]
        session.add(group)
        return
    existing = {m.photo_id for m in group.members}
    added = [p for p in copies if p.id not in existing]
    for p in added:
        group.members.append(DuplicateGroupMember(photo_id=p.id, similarity_pct=100))
    if added and group.status == "reviewed":
        group.status = "pending"  # a new copy appeared — needs another look
    group.keeper_photo_id = keeper
