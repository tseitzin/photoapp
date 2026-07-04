from pathlib import Path

from fastapi.testclient import TestClient

from tests.images import make_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _make_dupes(root: Path, copies: int = 3, name: str = "orig") -> Path:
    # Content must differ per name, or separately-named "originals" would be
    # byte-identical and merge into a single group.
    color = f"hsl({(ord(name[0]) * 47) % 360}, 65%, 45%)"
    original = make_image(root / f"{name}.jpg", color=color, size=(600, 400))
    for i in range(copies - 1):
        target = root / f"{name}_copy{i}.jpg"
        target.write_bytes(original.read_bytes())
    return original


def test_scan_builds_exact_group_with_keeper_and_members(
    client: TestClient, tmp_path: Path
) -> None:
    _make_dupes(tmp_path, copies=3)
    make_image(tmp_path / "unique.jpg", color="gold")
    _index(client, tmp_path)

    page = client.get("/api/duplicates/groups").json()

    assert page["total"] == 1
    group = page["items"][0]
    assert group["kind"] == "exact"
    assert group["status"] == "pending"
    assert len(group["members"]) == 3
    assert all(m["similarity_pct"] == 100 for m in group["members"])
    assert group["keeper_photo_id"] in [m["photo"]["id"] for m in group["members"]]
    assert group["reclaimable_bytes"] == 2 * group["members"][0]["photo"]["size_bytes"]


def test_rescan_preserves_group_identity_and_review_state(
    client: TestClient, tmp_path: Path
) -> None:
    _make_dupes(tmp_path, copies=2)
    _index(client, tmp_path)
    group = client.get("/api/duplicates/groups").json()["items"][0]
    keeper = group["keeper_photo_id"]
    other = next(m["photo"]["id"] for m in group["members"] if m["photo"]["id"] != keeper)
    decided = client.post(
        f"/api/duplicates/groups/{group['id']}/decisions",
        json={
            "decisions": [
                {"photo_id": keeper, "decision": "keep"},
                {"photo_id": other, "decision": "remove"},
            ]
        },
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "reviewed"

    assert client.post("/api/scans", json={}).status_code == 202
    after = client.get("/api/duplicates/groups").json()["items"][0]

    assert after["id"] == group["id"]
    assert after["status"] == "reviewed"
    decisions = {m["photo"]["id"]: m["decision"] for m in after["members"]}
    assert decisions == {keeper: "keep", other: "remove"}


def test_new_copy_in_reviewed_group_reopens_it(client: TestClient, tmp_path: Path) -> None:
    original = _make_dupes(tmp_path, copies=2)
    _index(client, tmp_path)
    group = client.get("/api/duplicates/groups").json()["items"][0]
    for member in group["members"]:
        decision = "keep" if member["photo"]["id"] == group["keeper_photo_id"] else "remove"
        client.post(
            f"/api/duplicates/groups/{group['id']}/decisions",
            json={"decisions": [{"photo_id": member["photo"]["id"], "decision": decision}]},
        )
    assert client.get(f"/api/duplicates/groups/{group['id']}").json()["status"] == "reviewed"

    (tmp_path / "third_copy.jpg").write_bytes(original.read_bytes())
    assert client.post("/api/scans", json={}).status_code == 202

    after = client.get(f"/api/duplicates/groups/{group['id']}").json()
    assert after["status"] == "pending"
    assert len(after["members"]) == 3


def test_group_disappears_when_duplicates_are_gone(client: TestClient, tmp_path: Path) -> None:
    original = _make_dupes(tmp_path, copies=2)
    copy = tmp_path / "orig_copy0.jpg"
    _index(client, tmp_path)
    assert client.get("/api/duplicates/groups").json()["total"] == 1

    copy.unlink()
    assert client.post("/api/scans", json={}).status_code == 202

    assert client.get("/api/duplicates/groups").json()["total"] == 0
    assert original.exists()


def test_rejects_decision_for_photo_outside_group(client: TestClient, tmp_path: Path) -> None:
    _make_dupes(tmp_path, copies=2)
    make_image(tmp_path / "unrelated.jpg", color="pink")
    _index(client, tmp_path)
    group = client.get("/api/duplicates/groups").json()["items"][0]
    outsider = next(
        p["id"]
        for p in client.get("/api/photos").json()["items"]
        if p["id"] not in [m["photo"]["id"] for m in group["members"]]
    )

    response = client.post(
        f"/api/duplicates/groups/{group['id']}/decisions",
        json={"decisions": [{"photo_id": outsider, "decision": "remove"}]},
    )

    assert response.status_code == 422


def test_refuses_to_remove_every_member_of_a_group(client: TestClient, tmp_path: Path) -> None:
    _make_dupes(tmp_path, copies=2)
    _index(client, tmp_path)
    group = client.get("/api/duplicates/groups").json()["items"][0]

    response = client.post(
        f"/api/duplicates/groups/{group['id']}/decisions",
        json={
            "decisions": [
                {"photo_id": m["photo"]["id"], "decision": "remove"} for m in group["members"]
            ]
        },
    )

    assert response.status_code == 422
    assert "keep at least one" in response.json()["detail"]


def test_undecided_reverts_a_decision_and_reopens_group(client: TestClient, tmp_path: Path) -> None:
    _make_dupes(tmp_path, copies=2)
    _index(client, tmp_path)
    group = client.get("/api/duplicates/groups").json()["items"][0]
    ids = [m["photo"]["id"] for m in group["members"]]
    client.post(
        f"/api/duplicates/groups/{group['id']}/decisions",
        json={
            "decisions": [
                {"photo_id": ids[0], "decision": "keep"},
                {"photo_id": ids[1], "decision": "remove"},
            ]
        },
    )

    reverted = client.post(
        f"/api/duplicates/groups/{group['id']}/decisions",
        json={"decisions": [{"photo_id": ids[1], "decision": "undecided"}]},
    ).json()

    assert reverted["status"] == "pending"
    decisions = {m["photo"]["id"]: m["decision"] for m in reverted["members"]}
    assert decisions[ids[1]] is None


def test_dismiss_and_summary(client: TestClient, tmp_path: Path) -> None:
    _make_dupes(tmp_path, copies=2, name="a")
    _make_dupes(tmp_path, copies=2, name="b")
    _index(client, tmp_path)
    groups = client.get("/api/duplicates/groups").json()["items"]
    client.post(f"/api/duplicates/groups/{groups[0]['id']}/dismiss")
    keeper = groups[1]["keeper_photo_id"]
    remove_id = next(m["photo"]["id"] for m in groups[1]["members"] if m["photo"]["id"] != keeper)
    client.post(
        f"/api/duplicates/groups/{groups[1]['id']}/decisions",
        json={"decisions": [{"photo_id": remove_id, "decision": "remove"}]},
    )

    summary = client.get("/api/duplicates/summary").json()

    assert summary["groups"] == 2
    assert summary["exact_groups"] == 2
    assert summary["dismissed_groups"] == 1
    assert summary["marked_remove_count"] == 1
    assert summary["marked_remove_bytes"] > 0


def test_kind_and_status_filters_paginate(client: TestClient, tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        _make_dupes(tmp_path, copies=2, name=name)
    _index(client, tmp_path)

    page = client.get("/api/duplicates/groups", params={"limit": 2, "kind": "exact"}).json()

    assert page["total"] == 3
    assert len(page["items"]) == 2
    rest = client.get(
        "/api/duplicates/groups", params={"limit": 2, "offset": 2, "kind": "exact"}
    ).json()
    assert len(rest["items"]) == 1
    assert client.get("/api/duplicates/groups", params={"kind": "similar"}).json()["total"] == 0
