"""Place names reach the database and the API, by both routes that set them."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Photo
from tests.images import gps_exif, make_image

# Boston City Hall — a coordinate the bundled dataset resolves precisely.
BOSTON = (42.3601, -71.0589)
# Mount Washington: the nearest named town is well away.
WILDERNESS = (44.2705, -71.3033)


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def test_a_scan_names_the_place_for_a_photo_with_coordinates(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "boston.jpg", gps_ifd_fields=gps_exif(*BOSTON))

    _index(client, tmp_path)

    photo = db_session.scalars(select(Photo)).one()
    assert photo.city == "Boston"
    assert photo.region == "Massachusetts"
    assert photo.country == "US"
    assert photo.place_distance_km is not None and photo.place_distance_km < 5


def test_a_photo_without_coordinates_gets_no_place(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "plain.jpg", color="tomato")

    _index(client, tmp_path)

    photo = db_session.scalars(select(Photo)).one()
    assert photo.latitude is None
    assert (photo.city, photo.region, photo.country, photo.place_distance_km) == (
        None,
        None,
        None,
        None,
    )


def test_the_place_is_on_the_photo_list_response(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "boston.jpg", gps_ifd_fields=gps_exif(*BOSTON))
    _index(client, tmp_path)

    item = client.get("/api/photos").json()["items"][0]

    assert item["city"] == "Boston"
    assert item["region"] == "Massachusetts"
    assert item["country"] == "US"
    assert item["place_distance_km"] < 5


def test_a_remote_photo_keeps_the_distance_so_the_ui_can_say_near(
    client: TestClient, tmp_path: Path
) -> None:
    make_image(tmp_path / "summit.jpg", gps_ifd_fields=gps_exif(*WILDERNESS))
    _index(client, tmp_path)

    item = client.get("/api/photos").json()["items"][0]

    assert item["region"] == "New Hampshire"
    assert item["place_distance_km"] > 5


def test_the_backfill_names_places_for_the_photos_it_finds(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """Photos indexed before this feature gain both coordinates and a place."""
    make_image(tmp_path / "boston.jpg", gps_ifd_fields=gps_exif(*BOSTON))
    _index(client, tmp_path)
    for photo in db_session.scalars(select(Photo)):
        photo.latitude = photo.longitude = None
        photo.city = photo.region = photo.country = None
        photo.place_distance_km = None
    db_session.commit()

    result = client.post("/api/maintenance/backfill-gps", json={}).json()

    assert result["updated"] == 1
    db_session.expire_all()
    photo = db_session.scalars(select(Photo)).one()
    assert photo.city == "Boston"
    assert photo.region == "Massachusetts"


def test_moving_a_photo_carries_the_freshly_geocoded_place_onto_the_kept_row(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """Move detection copies columns from the new row onto the surviving one.

    A column missing from that list is silently dropped, so the row has to start
    without a place — as photos indexed before this feature do — for the copy to
    be what is under test.
    """
    source = tmp_path / "a"
    make_image(source / "boston.jpg", gps_ifd_fields=gps_exif(*BOSTON))
    _index(client, tmp_path)
    original = db_session.scalars(select(Photo)).one()
    original_id = original.id
    original.city = original.region = original.country = None
    original.place_distance_km = None
    db_session.commit()

    (tmp_path / "b").mkdir()
    (source / "boston.jpg").rename(tmp_path / "b" / "boston.jpg")
    assert client.post("/api/scans", json={}).status_code == 202

    db_session.expire_all()
    photo = db_session.scalars(select(Photo)).one()
    assert photo.id == original_id  # same row, moved rather than re-added
    assert photo.city == "Boston"
    assert photo.region == "Massachusetts"
    assert photo.place_distance_km is not None
