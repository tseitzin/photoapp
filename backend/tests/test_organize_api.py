"""Organize API: preview without side effects, start/poll lifecycle, guards."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.repositories.organize import OrganizeRunRepository
from app.repositories.scans import ScanRepository
from app.services.organize import recover_interrupted_runs
from tests.images import make_image, make_textured_image

CAPTURED = {36867: "2024:07:15 14:30:22"}


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _request(root: Path, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "folders": [str(root / "inbox")],
        "destination": str(root / "Organized"),
        "mode": "date",
        "rename": False,
        "skip_duplicates": True,
    }
    body.update(overrides)
    return body


def test_preview_returns_counts_and_example_paths_without_moving_anything(
    client: TestClient, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg", exif_ifd_fields=CAPTURED)
    original = make_textured_image(tmp_path / "inbox" / "dup.jpg", seed=1)
    (tmp_path / "inbox" / "dup_copy.jpg").write_bytes(original.read_bytes())
    _index(client, tmp_path)

    response = client.post("/api/organize/preview", json=_request(tmp_path, rename=True))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["planned"] == 2  # keeper + a.jpg; the copy is skipped
    assert body["duplicates_in_set"] == 1
    assert body["duplicates_skipped"] == 1
    assert body["est_bytes"] > 0
    assert str(tmp_path / "Organized") in body["example_paths"][0]
    assert body["rename_example"]["new"] == "2024-07-15_143022.jpg"
    # nothing moved, nothing recorded
    assert (tmp_path / "inbox" / "a.jpg").is_file()
    assert client.get("/api/organize").json() == []


def test_start_returns_202_and_completes_via_polling(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg", exif_ifd_fields=CAPTURED)
    _index(client, tmp_path)

    started = client.post("/api/organize", json=_request(tmp_path))

    assert started.status_code == 202
    run_id = started.json()["id"]
    db_session.expire_all()  # the inline job ran in its own session
    polled = client.get(f"/api/organize/{run_id}").json()
    assert polled["status"] == "completed"
    assert polled["moved"] == 1
    assert polled["params"]["mode"] == "date"
    assert (tmp_path / "Organized" / "2024" / "07" / "a.jpg").is_file()


def test_start_refuses_while_a_scan_is_running(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg")
    _index(client, tmp_path)
    scans = ScanRepository(db_session)
    scans.mark_running(scans.create(None))  # a scan is mid-flight

    response = client.post("/api/organize", json=_request(tmp_path))

    assert response.status_code == 409
    assert "scan" in response.json()["detail"].lower()


def test_start_refuses_while_another_organize_is_active(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg")
    _index(client, tmp_path)
    runs = OrganizeRunRepository(db_session)
    runs.mark_running(runs.create(_request(tmp_path), "batch-1"))

    response = client.post("/api/organize", json=_request(tmp_path))

    assert response.status_code == 409
    assert "organize" in response.json()["detail"].lower()


def test_start_registers_an_outside_destination_and_organizes_into_it(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    library = tmp_path / "library"
    make_image(library / "inbox" / "a.jpg", exif_ifd_fields=CAPTURED)
    _index(client, library)
    destination = tmp_path / "elsewhere"

    response = client.post(
        "/api/organize",
        json={
            "folders": [str(library / "inbox")],
            "destination": str(destination),
            "mode": "date",
        },
    )

    assert response.status_code == 202
    db_session.expire_all()
    root_paths = [r["path"] for r in client.get("/api/scan-roots").json()]
    assert str(destination) in root_paths  # registered automatically
    assert (destination / "2024" / "07" / "a.jpg").is_file()


def test_preview_flags_a_destination_that_would_become_a_new_root(
    client: TestClient, tmp_path: Path
) -> None:
    library = tmp_path / "library"
    make_image(library / "inbox" / "a.jpg")
    _index(client, library)

    body = _request(library, destination=str(tmp_path / "elsewhere"))
    body["folders"] = [str(library / "inbox")]
    preview = client.post("/api/organize/preview", json=body).json()

    assert preview["destination_new_root"] is True
    # a dry run registers nothing
    assert [r["path"] for r in client.get("/api/scan-roots").json()] == [str(library)]


def test_start_refuses_a_destination_that_contains_an_existing_root(
    client: TestClient, tmp_path: Path
) -> None:
    library = tmp_path / "library"
    make_image(library / "inbox" / "a.jpg")
    _index(client, library)

    response = client.post(
        "/api/organize",
        json={
            "folders": [str(library / "inbox")],
            "destination": str(tmp_path),  # parent of the library root
            "mode": "date",
        },
    )

    assert response.status_code == 409
    assert "contains the existing scan root" in response.json()["detail"]


def test_interrupted_runs_are_recovered_as_failed_on_startup(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    runs = OrganizeRunRepository(db_session)
    runs.mark_running(runs.create(_request(tmp_path), "batch-1"))

    recovered = recover_interrupted_runs(db_session)

    assert recovered == 1
    run = client.get("/api/organize").json()[0]
    assert run["status"] == "failed"
    assert "restart" in run["message"].lower()


def test_file_operations_log_lists_organize_entries(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    make_image(tmp_path / "inbox" / "a.jpg", exif_ifd_fields=CAPTURED)
    _index(client, tmp_path)
    assert client.post("/api/organize", json=_request(tmp_path)).status_code == 202
    db_session.expire_all()

    page = client.get("/api/file-operations").json()

    ops = [item for item in page["items"] if item["op"] == "organize"]
    assert len(ops) == 1
    assert ops[0]["src_path"].endswith("a.jpg")
    assert ops[0]["dest_path"] == str(tmp_path / "Organized" / "2024" / "07" / "a.jpg")
