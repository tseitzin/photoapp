"""GPS backfill: fills only photos without coordinates, cursor-paginates."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Photo
from tests.images import gps_exif, make_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def test_backfill_updates_only_photos_without_coordinates(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "geo.jpg", gps_ifd_fields=gps_exif(47.6, 9.56))
    make_image(tmp_path / "plain.jpg", color="tomato")
    _index(client, tmp_path)
    # Simulate photos indexed before GPS extraction existed.
    for photo in db_session.scalars(select(Photo)):
        photo.latitude = None
        photo.longitude = None
    db_session.commit()

    result = client.post("/api/maintenance/backfill-gps", json={}).json()

    assert result["processed"] == 2
    assert result["updated"] == 1
    assert result["next_after_id"] is None
    assert result["remaining"] == 0
    db_session.expire_all()
    by_name = {p.filename: p for p in db_session.scalars(select(Photo))}
    assert by_name["geo.jpg"].latitude == pytest.approx(47.6, abs=1e-4)
    assert by_name["plain.jpg"].latitude is None


def test_backfill_does_not_touch_photos_that_already_have_coordinates(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "geo.jpg", gps_ifd_fields=gps_exif(47.6, 9.56))
    _index(client, tmp_path)  # the scan already stored coordinates

    result = client.post("/api/maintenance/backfill-gps", json={}).json()

    assert result["processed"] == 0
    assert result["updated"] == 0


def test_backfill_paginates_with_a_cursor_and_reports_remaining(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    for i, color in enumerate(["steelblue", "tomato", "seagreen"]):
        make_image(tmp_path / f"p{i}.jpg", color=color, gps_ifd_fields=gps_exif(10 + i, 20 + i))
    _index(client, tmp_path)
    for photo in db_session.scalars(select(Photo)):
        photo.latitude = None
        photo.longitude = None
    db_session.commit()

    first = client.post("/api/maintenance/backfill-gps", json={"limit": 2}).json()

    assert first["processed"] == 2
    assert first["updated"] == 2
    assert first["next_after_id"] is not None
    assert first["remaining"] == 1

    second = client.post(
        "/api/maintenance/backfill-gps", json={"after_id": first["next_after_id"], "limit": 2}
    ).json()

    assert second["processed"] == 1
    assert second["updated"] == 1
    assert second["next_after_id"] is None
    db_session.expire_all()
    assert all(p.latitude is not None for p in db_session.scalars(select(Photo)))
