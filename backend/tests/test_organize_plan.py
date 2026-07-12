"""Organize plan builder: destination computation, dedupe, collisions.

Planning is pure DB + computation (no per-file disk access) so previews stay
fast on large libraries; these tests pin the destination rules the user
approves in the preview.
"""

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.files.organize import OrganizeSpec, build_plan
from app.models import Photo
from app.services.errors import ValidationFailedError
from tests.images import make_image, make_textured_image

CAPTURED = {36867: "2024:07:15 14:30:22"}  # DateTimeOriginal in the Exif IFD


def _index(client: TestClient, *roots: Path) -> None:
    for root in roots:
        assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _spec(root: Path, folders: list[Path], **overrides: object) -> OrganizeSpec:
    params: dict[str, object] = {
        "folders": [str(f) for f in folders],
        "destination": str(root / "Organized"),
        "mode": "date",
        "rename": False,
        "skip_duplicates": True,
    }
    params.update(overrides)
    return OrganizeSpec.from_params(params)


def test_date_mode_sorts_into_year_month_folders(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg", exif_ifd_fields=CAPTURED)
    make_image(
        tmp_path / "inbox" / "b.jpg",
        color="tomato",
        exif_ifd_fields={36867: "2023:12:01 09:00:00"},
    )
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"]))

    dests = sorted(move.dest for move in plan.moves)
    assert dests == [
        str(tmp_path / "Organized" / "2023" / "12" / "b.jpg"),
        str(tmp_path / "Organized" / "2024" / "07" / "a.jpg"),
    ]
    assert plan.undated == 0
    assert plan.est_bytes > 0


def test_photos_without_capture_date_go_to_undated(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "screenshot.png")  # no EXIF at all
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"]))

    assert [move.dest for move in plan.moves] == [
        str(tmp_path / "Organized" / "Undated" / "screenshot.png")
    ]
    assert plan.undated == 1


def test_keep_mode_preserves_subfolders_under_the_selected_folder_name(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "vacation" / "day1" / "beach.jpg")
    make_image(tmp_path / "vacation" / "top.jpg", color="tomato")
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "vacation"], mode="keep"))

    assert sorted(move.dest for move in plan.moves) == [
        str(tmp_path / "Organized" / "vacation" / "day1" / "beach.jpg"),
        str(tmp_path / "Organized" / "vacation" / "top.jpg"),
    ]


def test_camera_mode_groups_by_model_with_unknown_fallback(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg", exif_fields={272: "Canon EOS R5"})
    make_image(tmp_path / "inbox" / "b.jpg", color="tomato")  # no camera
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"], mode="camera"))

    assert sorted(move.dest for move in plan.moves) == [
        str(tmp_path / "Organized" / "Canon EOS R5" / "a.jpg"),
        str(tmp_path / "Organized" / "Unknown camera" / "b.jpg"),
    ]


def test_camera_names_with_slashes_are_sanitized(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg", exif_fields={272: "PowerShot A/B"})
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"], mode="camera"))

    assert plan.moves[0].dest == str(tmp_path / "Organized" / "PowerShot A-B" / "a.jpg")


def test_rename_uses_capture_timestamp_and_keeps_original_extension(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "IMG_0001.jpg", exif_ifd_fields=CAPTURED)
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"], rename=True))

    assert plan.moves[0].dest == str(
        tmp_path / "Organized" / "2024" / "07" / "2024-07-15_143022.jpg"
    )
    assert plan.rename_example == ("IMG_0001.jpg", "2024-07-15_143022.jpg")


def test_undated_photos_keep_their_filename_when_renaming(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "screenshot.png")
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"], rename=True))

    assert plan.moves[0].dest == str(tmp_path / "Organized" / "Undated" / "screenshot.png")


def test_same_second_renames_get_numeric_suffixes(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_textured_image(tmp_path / "inbox" / "burst1.jpg", seed=1)
    make_textured_image(tmp_path / "inbox" / "burst2.jpg", seed=2)
    _index(client, tmp_path)
    # Textured helper writes no EXIF; stamp both with the same capture second.
    for photo in db_session.query(Photo).all():
        photo.captured_at = datetime(2024, 7, 15, 14, 30, 22)  # noqa: DTZ001
    db_session.commit()

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"], rename=True))

    names = sorted(Path(move.dest).name for move in plan.moves)
    assert names == ["2024-07-15_143022.jpg", "2024-07-15_143022_01.jpg"]


def test_nested_selected_folders_are_not_double_counted(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "vacation" / "day1" / "beach.jpg")
    _index(client, tmp_path)

    plan = build_plan(
        db_session,
        _spec(tmp_path, [tmp_path / "vacation", tmp_path / "vacation" / "day1"], mode="keep"),
    )

    assert plan.total == 1
    assert [move.dest for move in plan.moves] == [
        str(tmp_path / "Organized" / "vacation" / "day1" / "beach.jpg")
    ]


def test_skip_duplicates_moves_only_the_keeper(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    original = make_textured_image(tmp_path / "inbox" / "dup.jpg", seed=1)
    (tmp_path / "inbox" / "dup_copy.jpg").write_bytes(original.read_bytes())
    (tmp_path / "inbox" / "dup_copy2.jpg").write_bytes(original.read_bytes())
    _index(client, tmp_path)
    group = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()["items"][0]

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"]))

    assert plan.duplicates_in_set == 2
    assert plan.duplicates_skipped == 2
    assert [move.photo_id for move in plan.moves] == [group["keeper_photo_id"]]


def test_duplicate_count_is_reported_even_when_skip_is_off(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    original = make_textured_image(tmp_path / "inbox" / "dup.jpg", seed=1)
    (tmp_path / "inbox" / "dup_copy.jpg").write_bytes(original.read_bytes())
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"], skip_duplicates=False))

    assert plan.duplicates_in_set == 1
    assert plan.duplicates_skipped == 0
    assert len(plan.moves) == 2  # both copies move


def test_photo_already_at_target_path_is_a_noop(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "vacation" / "x.jpg")
    _index(client, tmp_path)

    # keep-mode with the root itself as destination maps the photo onto its own path
    plan = build_plan(
        db_session,
        _spec(tmp_path, [tmp_path / "vacation"], mode="keep", destination=str(tmp_path)),
    )

    assert plan.moves == []
    assert plan.already_organized == 1


def test_collision_with_a_quarantined_photos_db_path_gets_a_suffix(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "x.png")
    blocker = make_image(tmp_path / "Organized" / "Undated" / "x.png", color="tomato")
    _index(client, tmp_path)
    blocker_id = next(
        p["id"] for p in client.get("/api/photos").json()["items"] if p["path"] == str(blocker)
    )
    # Quarantine frees the disk slot but the DB row keeps its unique path.
    assert client.post("/api/quarantine", json={"photo_ids": [blocker_id]}).status_code == 200

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"]))

    assert [move.dest for move in plan.moves] == [
        str(tmp_path / "Organized" / "Undated" / "x_01.png")
    ]


def test_destination_outside_scan_roots_is_flagged_as_a_new_root(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    library = tmp_path / "library"
    make_image(library / "inbox" / "a.png")
    _index(client, library)

    plan = build_plan(
        db_session,
        _spec(library, [library / "inbox"], destination=str(tmp_path / "elsewhere")),
    )

    assert plan.destination_new_root is True
    assert [move.dest for move in plan.moves] == [str(tmp_path / "elsewhere" / "Undated" / "a.png")]


def test_destination_inside_a_scan_root_is_not_flagged(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.png")
    _index(client, tmp_path)

    plan = build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"]))

    assert plan.destination_new_root is False


def test_destination_inside_the_quarantine_folder_is_rejected(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    from app.core.config import get_settings

    make_image(tmp_path / "inbox" / "a.png")
    _index(client, tmp_path)
    quarantined_dest = str(get_settings().quarantine_dir / "sneaky")

    with pytest.raises(ValidationFailedError, match="quarantine"):
        build_plan(db_session, _spec(tmp_path, [tmp_path / "inbox"], destination=quarantined_dest))
