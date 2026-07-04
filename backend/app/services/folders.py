"""Folder tree derived from indexed photo paths.

Folders are not a table — they are an aggregation over photos.path, rebuilt
per request (one GROUP BY plus in-memory rollup; fine at 100k+ photos for a
single user, and never stale).
"""

from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Photo
from app.repositories.scan_roots import ScanRootRepository


@dataclass
class FolderNode:
    path: str
    name: str
    parent_path: str | None
    depth: int
    photo_count: int  # includes all descendants
    direct_count: int
    has_children: bool
    root_id: int


def build_folder_tree(session: Session) -> list[FolderNode]:
    roots = ScanRootRepository(session).list_all()
    dir_rows = session.execute(
        select(
            func.regexp_replace(Photo.path, r"/[^/]*$", "").label("dir"),
            func.count(),
        )
        .where(Photo.status != "quarantined")
        .group_by("dir")
    ).all()

    nodes: dict[str, FolderNode] = {}
    for root in roots:
        root_path = root.path
        for dir_path, direct_count in dir_rows:
            if dir_path != root_path and not dir_path.startswith(root_path + "/"):
                continue
            # Materialize the dir and every ancestor up to the root, rolling
            # counts upward so parents show recursive totals.
            current = dir_path
            remaining = int(direct_count)
            while True:
                node = nodes.get(current)
                if node is None:
                    parent = None if current == root_path else str(PurePosixPath(current).parent)
                    node = FolderNode(
                        path=current,
                        name=PurePosixPath(current).name or current,
                        parent_path=parent,
                        depth=0 if current == root_path else current[len(root_path) :].count("/"),
                        photo_count=0,
                        direct_count=0,
                        has_children=False,
                        root_id=root.id,
                    )
                    nodes[current] = node
                node.photo_count += remaining
                if current == dir_path:
                    node.direct_count += remaining
                if current == root_path:
                    break
                current = str(PurePosixPath(current).parent)

    for node in nodes.values():
        if node.parent_path and node.parent_path in nodes:
            nodes[node.parent_path].has_children = True
    return sorted(nodes.values(), key=lambda n: n.path)
