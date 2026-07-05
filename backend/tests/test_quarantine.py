"""Safety tests for quarantine / restore / permanent delete.

These cover the only code in the app allowed to move or delete user files,
including path-traversal and symlink-escape attempts simulated by tampering
with DB rows directly (the filesystem attack surface an API caller can't reach).
"""

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import FileOperation, Photo
from tests.images import make_textured_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _photo_ids(client: TestClient) -> dict[str, int]:
    return {
        p["filename"]: p["id"]
        for p in client.get("/api/photos", params={"limit": 200}).json()["items"]
    }


def _quarantine_slot(original: Path) -> Path:
    # realpath both sides: on macOS /var and /tmp are symlinks into /private.
    qdir = Path(os.path.realpath(get_settings().quarantine_dir))
    resolved = original.resolve() if original.exists() else Path(os.path.realpath(original))
    return qdir / resolved.relative_to(resolved.anchor)


class TestQuarantine:
    def test_moves_file_to_quarantine_and_records_audit(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        photo_path = make_textured_image(tmp_path / "2024/victim.jpg", seed=1)
        make_textured_image(tmp_path / "keeper.jpg", seed=2)
        _index(client, tmp_path)
        ids = _photo_ids(client)

        response = client.post("/api/quarantine", json={"photo_ids": [ids["victim.jpg"]]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["succeeded"] == 1 and body["failed"] == 0
        assert not photo_path.exists(), "original must be gone from the library"
        slot = _quarantine_slot(photo_path)
        assert slot.is_file(), "file must exist in its quarantine slot"

        photo = db_session.get(Photo, ids["victim.jpg"])
        assert photo is not None and photo.status == "quarantined"
        assert photo.path == str(photo_path), "original path retained for restore"

        op = db_session.scalars(select(FileOperation)).one()
        assert op.op == "quarantine"
        assert op.src_path == str(photo_path)
        assert op.dest_path == str(slot)
        assert op.batch_id == body["batch_id"]

    def test_partial_batch_failure_reports_per_item(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        gone = make_textured_image(tmp_path / "gone.jpg", seed=1)
        make_textured_image(tmp_path / "ok.jpg", seed=2)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        gone.unlink()  # vanishes after indexing, before quarantine

        body = client.post(
            "/api/quarantine", json={"photo_ids": [ids["gone.jpg"], ids["ok.jpg"]]}
        ).json()

        assert body["succeeded"] == 1 and body["failed"] == 1
        by_id = {r["photo_id"]: r for r in body["results"]}
        assert by_id[ids["gone.jpg"]]["ok"] is False
        assert by_id[ids["ok.jpg"]]["ok"] is True

    def test_rejects_photo_whose_path_escapes_roots_via_traversal(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        outside = make_textured_image(tmp_path / "outside/secret.jpg", seed=3)
        root = tmp_path / "root"
        make_textured_image(root / "inside.jpg", seed=1)
        _index(client, root)
        ids = _photo_ids(client)
        photo = db_session.get(Photo, ids["inside.jpg"])
        assert photo is not None
        photo.path = str(root / ".." / "outside" / "secret.jpg")  # tampered
        db_session.commit()

        body = client.post("/api/quarantine", json={"photo_ids": [photo.id]}).json()

        assert body["failed"] == 1
        assert "outside approved directories" in body["results"][0]["error"]
        assert outside.exists(), "the file outside the root must be untouched"

    def test_rejects_symlink_escape(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        outside = make_textured_image(tmp_path / "outside/secret.jpg", seed=3)
        root = tmp_path / "root"
        make_textured_image(root / "inside.jpg", seed=1)
        _index(client, root)
        os.symlink(tmp_path / "outside", root / "link")
        ids = _photo_ids(client)
        photo = db_session.get(Photo, ids["inside.jpg"])
        assert photo is not None
        photo.path = str(root / "link" / "secret.jpg")  # inside root only textually
        db_session.commit()

        body = client.post("/api/quarantine", json={"photo_ids": [photo.id]}).json()

        assert body["failed"] == 1
        assert "outside approved directories" in body["results"][0]["error"]
        assert outside.exists()

    def test_refuses_to_wipe_a_whole_duplicate_group_without_force(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        original = make_textured_image(tmp_path / "a.jpg", seed=1)
        (tmp_path / "b.jpg").write_bytes(original.read_bytes())
        _index(client, tmp_path)
        ids = _photo_ids(client)

        refused = client.post("/api/quarantine", json={"photo_ids": [ids["a.jpg"], ids["b.jpg"]]})
        assert refused.status_code == 409
        assert "every remaining photo" in refused.json()["detail"]
        assert original.exists()

        forced = client.post(
            "/api/quarantine",
            json={"photo_ids": [ids["a.jpg"], ids["b.jpg"]], "force": True},
        )
        assert forced.status_code == 200
        assert forced.json()["succeeded"] == 2

    def test_quarantining_one_duplicate_dissolves_the_group(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        original = make_textured_image(tmp_path / "a.jpg", seed=1)
        (tmp_path / "b.jpg").write_bytes(original.read_bytes())
        _index(client, tmp_path)
        ids = _photo_ids(client)
        assert client.get("/api/duplicates/groups").json()["total"] == 1

        client.post("/api/quarantine", json={"photo_ids": [ids["b.jpg"]]})

        assert client.get("/api/duplicates/groups").json()["total"] == 0

    def test_already_quarantined_photo_is_rejected_per_item(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        make_textured_image(tmp_path / "a.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        client.post("/api/quarantine", json={"photo_ids": [ids["a.jpg"]]})

        body = client.post("/api/quarantine", json={"photo_ids": [ids["a.jpg"]]}).json()

        assert body["failed"] == 1
        assert "not active" in body["results"][0]["error"]


class TestRestore:
    def test_restore_puts_the_file_back_and_reactivates(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        photo_path = make_textured_image(tmp_path / "2024/back.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        client.post("/api/quarantine", json={"photo_ids": [ids["back.jpg"]]})
        assert not photo_path.exists()

        body = client.post("/api/quarantine/restore", json={"photo_ids": [ids["back.jpg"]]}).json()

        assert body["succeeded"] == 1
        assert photo_path.is_file(), "file must be back at its original path"
        assert not _quarantine_slot(photo_path).exists()
        photo = db_session.get(Photo, ids["back.jpg"])
        assert photo is not None and photo.status == "active"
        ops = [op.op for op in db_session.scalars(select(FileOperation)).all()]
        assert ops == ["quarantine", "restore"]

    def test_restore_never_overwrites_an_existing_file(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        photo_path = make_textured_image(tmp_path / "a.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        client.post("/api/quarantine", json={"photo_ids": [ids["a.jpg"]]})
        make_textured_image(photo_path, seed=9)  # new file at the old path

        body = client.post("/api/quarantine/restore", json={"photo_ids": [ids["a.jpg"]]}).json()

        assert body["failed"] == 1
        assert "already exists" in body["results"][0]["error"]
        assert _quarantine_slot(photo_path).exists(), "quarantined copy must remain"

    def test_restore_of_active_photo_is_rejected(self, client: TestClient, tmp_path: Path) -> None:
        make_textured_image(tmp_path / "a.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)

        body = client.post("/api/quarantine/restore", json={"photo_ids": [ids["a.jpg"]]}).json()

        assert body["failed"] == 1
        assert "not quarantined" in body["results"][0]["error"]

    def test_quarantine_then_restore_round_trip_preserves_bytes(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        photo_path = make_textured_image(tmp_path / "roundtrip.jpg", seed=1)
        original_bytes = photo_path.read_bytes()
        _index(client, tmp_path)
        ids = _photo_ids(client)

        client.post("/api/quarantine", json={"photo_ids": [ids["roundtrip.jpg"]]})
        client.post("/api/quarantine/restore", json={"photo_ids": [ids["roundtrip.jpg"]]})

        assert photo_path.read_bytes() == original_bytes


class TestPermanentDelete:
    def test_requires_explicit_confirm(self, client: TestClient, tmp_path: Path) -> None:
        make_textured_image(tmp_path / "a.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        client.post("/api/quarantine", json={"photo_ids": [ids["a.jpg"]]})

        response = client.post("/api/quarantine/delete", json={"photo_ids": [ids["a.jpg"]]})

        assert response.status_code == 422
        assert "confirm" in response.json()["detail"]

    def test_refuses_active_photos(self, client: TestClient, tmp_path: Path) -> None:
        photo_path = make_textured_image(tmp_path / "a.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)

        body = client.post(
            "/api/quarantine/delete",
            json={"photo_ids": [ids["a.jpg"]], "confirm": True},
        ).json()

        assert body["failed"] == 1
        assert "Only quarantined" in body["results"][0]["error"]
        assert photo_path.exists()

    def test_deletes_quarantined_file_and_drops_row_keeping_audit(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        photo_path = make_textured_image(tmp_path / "doomed.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        client.post("/api/quarantine", json={"photo_ids": [ids["doomed.jpg"]]})
        slot = _quarantine_slot(photo_path)
        assert slot.exists()

        body = client.post(
            "/api/quarantine/delete",
            json={"photo_ids": [ids["doomed.jpg"]], "confirm": True},
        ).json()

        assert body["succeeded"] == 1
        assert not slot.exists()
        assert db_session.get(Photo, ids["doomed.jpg"]) is None
        ops = db_session.scalars(select(FileOperation).order_by(FileOperation.id)).all()
        assert [op.op for op in ops] == ["quarantine", "delete"]
        assert ops[-1].photo_id is None, "audit survives the photo row via SET NULL"
        assert ops[-1].src_path == str(slot)

    def test_refuses_tampered_target_outside_quarantine_dir(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        photo_path = make_textured_image(tmp_path / "a.jpg", seed=1)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        client.post("/api/quarantine", json={"photo_ids": [ids["a.jpg"]]})
        precious = make_textured_image(tmp_path / "precious.jpg", seed=5)
        op = db_session.scalars(select(FileOperation)).one()
        op.dest_path = str(precious)  # tampered audit row
        db_session.commit()

        body = client.post(
            "/api/quarantine/delete",
            json={"photo_ids": [ids["a.jpg"]], "confirm": True},
        ).json()

        assert body["failed"] == 1
        assert "outside approved directories" in body["results"][0]["error"]
        assert precious.exists(), "tampered target must not be deleted"
        assert _quarantine_slot(photo_path).exists()


class TestAuditAndMarked:
    def test_file_operations_endpoint_pages_newest_first(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        for i, name in enumerate(("a.jpg", "b.jpg")):
            make_textured_image(tmp_path / name, seed=i + 1)
        _index(client, tmp_path)
        ids = _photo_ids(client)
        client.post("/api/quarantine", json={"photo_ids": [ids["a.jpg"]]})
        client.post("/api/quarantine/restore", json={"photo_ids": [ids["a.jpg"]]})

        page = client.get("/api/file-operations").json()

        assert page["total"] == 2
        assert [op["op"] for op in page["items"]] == ["restore", "quarantine"]

    def test_marked_endpoint_lists_only_active_remove_decisions(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        original = make_textured_image(tmp_path / "a.jpg", seed=1)
        (tmp_path / "b.jpg").write_bytes(original.read_bytes())
        _index(client, tmp_path)
        group = client.get("/api/duplicates/groups").json()["items"][0]
        keeper = group["keeper_photo_id"]
        loser = next(m["photo"]["id"] for m in group["members"] if m["photo"]["id"] != keeper)
        client.post(
            f"/api/duplicates/groups/{group['id']}/decisions",
            json={
                "decisions": [
                    {"photo_id": keeper, "decision": "keep"},
                    {"photo_id": loser, "decision": "remove"},
                ]
            },
        )

        marked = client.get("/api/duplicates/marked").json()
        assert [p["id"] for p in marked] == [loser]

        client.post("/api/quarantine", json={"photo_ids": [loser]})
        assert client.get("/api/duplicates/marked").json() == []


class TestResetDeletionHistory:
    def test_reset_zeroes_the_tally_and_clears_removed_file_history(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        make_textured_image(tmp_path / "gone.jpg", seed=1)
        make_textured_image(tmp_path / "keep.jpg", seed=2)
        _index(client, tmp_path)
        gone = _photo_ids(client)["gone.jpg"]
        client.post("/api/quarantine", json={"photo_ids": [gone]})
        client.post("/api/quarantine/delete", json={"photo_ids": [gone], "confirm": True})
        assert client.get("/api/stats").json()["deleted_count"] == 1

        reset = client.post("/api/file-operations/reset")

        assert reset.status_code == 200
        # one delete row + the stale quarantine row for the removed photo
        assert reset.json()["cleared"] == 2
        stats = client.get("/api/stats").json()
        assert stats["deleted_count"] == 0
        assert stats["space_saved_bytes"] == 0
        assert client.get("/api/file-operations").json()["total"] == 0

    def test_reset_keeps_history_for_currently_quarantined_photos(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        make_textured_image(tmp_path / "held.jpg", seed=1)
        _index(client, tmp_path)
        held = _photo_ids(client)["held.jpg"]
        client.post("/api/quarantine", json={"photo_ids": [held]})

        cleared = client.post("/api/file-operations/reset").json()["cleared"]

        assert cleared == 0  # the photo still exists, so its record stays
        # restore still works because its quarantine record was preserved
        restored = client.post("/api/quarantine/restore", json={"photo_ids": [held]})
        assert restored.json()["succeeded"] == 1
