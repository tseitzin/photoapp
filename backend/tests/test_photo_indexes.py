"""The Library's query indexes exist, and the model and migration agree.

Tests build the schema with Base.metadata.create_all while production builds it
with Alembic, so the two definitions can drift silently — and a missing index
costs nothing at 4k photos and everything at 50k. These tests pin both sides.
"""

import importlib.util
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0013_photo_query_indexes.py"
)


def _migration_index_names() -> set[str]:
    """Index names migration 0013 creates (its module name isn't importable)."""
    spec = importlib.util.spec_from_file_location("migration_0013", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name for name, _ in module._INDEXES}


def test_every_index_the_migration_creates_is_declared_on_the_model(db_engine: Engine) -> None:
    on_model = {index["name"] for index in inspect(db_engine).get_indexes("photos")}

    assert _migration_index_names() <= on_model


def test_the_library_filter_and_sort_indexes_exist(db_engine: Engine) -> None:
    names = {index["name"] for index in inspect(db_engine).get_indexes("photos")}

    assert {
        "ix_photos_status_captured_desc",  # default sort
        "ix_photos_status_captured_asc",
        "ix_photos_status_filename",  # name_asc / name_desc
        "ix_photos_status_size",  # size_asc / size_desc
        "ix_photos_path_prefix",  # folder filter
        "ix_photos_filename_trgm",  # filename search
    } <= names


def test_status_has_no_index_of_its_own(db_engine: Engine) -> None:
    """It leads every composite; alone it has no selectivity (all rows active)."""
    indexes = inspect(db_engine).get_indexes("photos")

    assert not any(index["column_names"] == ["status"] for index in indexes)


def test_the_marked_for_deletion_index_is_partial(db_engine: Engine) -> None:
    """A plain b-tree would index every row to find the handful that are flagged."""
    with db_engine.connect() as conn:
        definition = conn.scalar(
            text(
                "select indexdef from pg_indexes where indexname = 'ix_photos_marked_for_deletion'"
            )
        )

    assert definition is not None
    assert "WHERE marked_for_deletion" in definition
