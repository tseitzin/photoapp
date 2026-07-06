from pathlib import Path

from fastapi.testclient import TestClient

from tests.images import make_textured_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _ids(client: TestClient) -> dict[str, int]:
    return {p["filename"]: p["id"] for p in client.get("/api/photos").json()["items"]}


def test_marking_a_photo_flags_it_and_lists_it_for_removal(
    client: TestClient, tmp_path: Path
) -> None:
    make_textured_image(tmp_path / "keep.jpg", seed=1)
    make_textured_image(tmp_path / "junk.jpg", seed=2)
    _index(client, tmp_path)
    junk = _ids(client)["junk.jpg"]

    response = client.post("/api/photos/mark", json={"photo_ids": [junk]})

    assert response.status_code == 200
    assert response.json() == {"marked": True, "affected": 1}
    # the photo now reports the flag in listings
    listed = {p["filename"]: p for p in client.get("/api/photos").json()["items"]}
    assert listed["junk.jpg"]["marked_for_deletion"] is True
    assert listed["keep.jpg"]["marked_for_deletion"] is False
    # and it shows up in the removal work-list
    marked = client.get("/api/photos/marked").json()
    assert [p["id"] for p in marked] == [junk]


def test_unmarking_removes_it_from_the_work_list(client: TestClient, tmp_path: Path) -> None:
    make_textured_image(tmp_path / "junk.jpg", seed=1)
    _index(client, tmp_path)
    junk = _ids(client)["junk.jpg"]
    client.post("/api/photos/mark", json={"photo_ids": [junk]})

    unmark = client.post("/api/photos/unmark", json={"photo_ids": [junk]})

    assert unmark.json() == {"marked": False, "affected": 1}
    assert client.get("/api/photos/marked").json() == []


def test_marked_work_list_unions_library_marks_and_duplicate_removes(
    client: TestClient, tmp_path: Path
) -> None:
    # a library-marked standalone photo
    make_textured_image(tmp_path / "solo.jpg", seed=1)
    # a duplicate pair; the non-keeper gets a 'remove' decision
    original = make_textured_image(tmp_path / "a.jpg", seed=2)
    (tmp_path / "b.jpg").write_bytes(original.read_bytes())
    _index(client, tmp_path)
    ids = _ids(client)
    client.post("/api/photos/mark", json={"photo_ids": [ids["solo.jpg"]]})
    group = client.get("/api/duplicates/groups").json()["items"][0]
    keeper = group["keeper_photo_id"]
    loser = next(m["photo"]["id"] for m in group["members"] if m["photo"]["id"] != keeper)
    client.post(
        f"/api/duplicates/groups/{group['id']}/decisions",
        json={"decisions": [{"photo_id": loser, "decision": "remove"}]},
    )

    marked_ids = {p["id"] for p in client.get("/api/photos/marked").json()}

    assert marked_ids == {ids["solo.jpg"], loser}


def test_marked_photo_flows_through_quarantine_and_clears_the_mark(
    client: TestClient, tmp_path: Path
) -> None:
    make_textured_image(tmp_path / "junk.jpg", seed=1)
    _index(client, tmp_path)
    junk = _ids(client)["junk.jpg"]
    client.post("/api/photos/mark", json={"photo_ids": [junk]})

    client.post("/api/quarantine", json={"photo_ids": [junk]})

    # gone from the active work-list (now quarantined) and the flag is cleared
    assert client.get("/api/photos/marked").json() == []
    detail = client.get(f"/api/photos/{junk}").json()
    assert detail["status"] == "quarantined"
    assert detail["marked_for_deletion"] is False


def test_mark_only_affects_active_photos(client: TestClient, tmp_path: Path) -> None:
    make_textured_image(tmp_path / "junk.jpg", seed=1)
    _index(client, tmp_path)
    junk = _ids(client)["junk.jpg"]
    client.post("/api/quarantine", json={"photo_ids": [junk]})  # now quarantined

    result = client.post("/api/photos/mark", json={"photo_ids": [junk]}).json()

    assert result["affected"] == 0
