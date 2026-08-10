"""Where the library lives, so a second location is visible before it exists.

A real library ended up as the same date structure in two places because
nothing compared the chosen destination against where the photos already were.
The split was only noticeable afterwards, by browsing.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.jobs.runner import InlineJobRunner
from app.models import Photo, ScanRoot
from app.services.organize import OrganizeService


@pytest.fixture(autouse=True)
def root(db_session: Session) -> ScanRoot:
    scan_root = ScanRoot(path="/lib", enabled=True)
    db_session.add(scan_root)
    db_session.flush()
    return scan_root


def service(db_session: Session) -> OrganizeService:
    return OrganizeService(db_session, InlineJobRunner(), lambda: db_session)


def add_photo(db_session: Session, path: str, status: str = "active") -> Photo:
    root_id = db_session.query(ScanRoot).filter_by(path="/lib").one().id
    photo = Photo(
        path=path,
        filename=path.rsplit("/", 1)[-1],
        root_id=root_id,
        ext="jpg",
        mime="image/jpeg",
        size_bytes=1000,
        mtime_ns=1,
        status=status,
        captured_at=datetime(2019, 7, 4, tzinfo=UTC),
    )
    db_session.add(photo)
    db_session.flush()
    return photo


def test_a_date_organized_tree_reports_its_destination_not_every_month(
    db_session: Session,
) -> None:
    """Otherwise one library reads as a hundred locations, one per month."""
    for month in ("01", "02", "03"):
        add_photo(db_session, f"/lib/Photos/2019/{month}/a{month}.jpg")
    add_photo(db_session, "/lib/Photos/2020/11/b.jpg")

    assert service(db_session).library_layout() == [("/lib/Photos", 4)]


def test_the_undated_bucket_belongs_to_its_destination_too(db_session: Session) -> None:
    add_photo(db_session, "/lib/Photos/2019/07/a.jpg")
    add_photo(db_session, "/lib/Photos/Undated/b.jpg")

    assert service(db_session).library_layout() == [("/lib/Photos", 2)]


def test_two_organized_trees_are_reported_separately_largest_first(
    db_session: Session,
) -> None:
    """The exact situation this is meant to make visible."""
    for index in range(3):
        add_photo(db_session, f"/lib/Camera Roll/Organized/2019/07/a{index}.jpg")
    add_photo(db_session, "/lib/Updated/2006/03/b.jpg")

    assert service(db_session).library_layout() == [
        ("/lib/Camera Roll/Organized", 3),
        ("/lib/Updated", 1),
    ]


def test_loose_photos_report_the_folder_they_are_actually_in(db_session: Session) -> None:
    """A folder that isn't a date bucket is its own location — that is how the
    five photos left behind by a skip_duplicates run showed up."""
    add_photo(db_session, "/lib/Photos/2019/07/a.jpg")
    add_photo(db_session, "/lib/Camera Roll/loose.jpg")

    assert service(db_session).library_layout() == [
        ("/lib/Camera Roll", 1),
        ("/lib/Photos", 1),
    ]


def test_a_folder_that_merely_looks_like_a_date_is_not_mistaken_for_one(
    db_session: Session,
) -> None:
    """Only a four-digit year over a two-digit month is a date bucket."""
    add_photo(db_session, "/lib/Photos/2019/7/a.jpg")  # single-digit month
    add_photo(db_session, "/lib/Photos/201/07/b.jpg")  # three-digit "year"

    assert service(db_session).library_layout() == [
        ("/lib/Photos/201/07", 1),
        ("/lib/Photos/2019/7", 1),
    ]


def test_quarantined_and_missing_photos_are_not_counted(db_session: Session) -> None:
    """The layout describes where the live library is, not where it has been."""
    add_photo(db_session, "/lib/Photos/2019/07/a.jpg")
    add_photo(db_session, "/lib/Old/2019/07/b.jpg", status="quarantined")
    add_photo(db_session, "/lib/Old/2019/07/c.jpg", status="missing")

    assert service(db_session).library_layout() == [("/lib/Photos", 1)]


def test_an_empty_library_has_no_locations(db_session: Session) -> None:
    assert service(db_session).library_layout() == []


def test_the_endpoint_reports_locations_and_a_total(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from tests.images import make_textured_image

    make_textured_image(tmp_path / "a.jpg", seed=1)
    make_textured_image(tmp_path / "b.jpg", seed=2)
    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202

    body = client.get("/api/organize/layout").json()

    assert body["total"] == 2
    assert body["locations"] == [{"path": str(tmp_path), "photos": 2}]


def test_layout_is_not_parsed_as_a_run_id(client) -> None:  # type: ignore[no-untyped-def]
    """/layout must be declared before /{run_id} or FastAPI 422s on the path."""
    assert client.get("/api/organize/layout").status_code == 200
