"""Incremental duplicate-group updates on quarantine/restore/delete.

These replace the per-batch full rebuild; verify the group state stays correct
without re-deriving the whole library.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.images import make_textured_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def _make_copies(root: Path, n: int, name: str = "dup") -> None:
    original = make_textured_image(root / f"{name}.jpg", seed=1, size=(800, 600))
    for i in range(n - 1):
        (root / f"{name}_{i}.jpg").write_bytes(original.read_bytes())


def _exact_group(client: TestClient) -> dict | None:
    items = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()["items"]
    return items[0] if items else None


def test_quarantining_one_of_three_copies_shrinks_but_keeps_the_group(
    client: TestClient, tmp_path: Path
) -> None:
    _make_copies(tmp_path, 3)
    _index(client, tmp_path)
    group = _exact_group(client)
    assert group is not None and len(group["members"]) == 3
    victim = group["members"][0]["photo"]["id"]

    assert client.post("/api/quarantine", json={"photo_ids": [victim]}).status_code == 200

    after = _exact_group(client)
    assert after is not None
    assert len(after["members"]) == 2
    assert victim not in [m["photo"]["id"] for m in after["members"]]


def test_quarantining_the_last_pair_member_dissolves_the_group(
    client: TestClient, tmp_path: Path
) -> None:
    _make_copies(tmp_path, 2)
    _index(client, tmp_path)
    victim = _exact_group(client)["members"][0]["photo"]["id"]  # type: ignore[index]

    client.post("/api/quarantine", json={"photo_ids": [victim]})

    assert _exact_group(client) is None


def test_quarantining_the_keeper_reassigns_it_to_a_survivor(
    client: TestClient, tmp_path: Path
) -> None:
    _make_copies(tmp_path, 3)
    _index(client, tmp_path)
    group = _exact_group(client)
    assert group is not None
    keeper = group["keeper_photo_id"]

    client.post("/api/quarantine", json={"photo_ids": [keeper]})

    after = _exact_group(client)
    assert after is not None
    assert after["keeper_photo_id"] != keeper
    assert after["keeper_photo_id"] in [m["photo"]["id"] for m in after["members"]]


def test_restore_reforms_an_exact_group(client: TestClient, tmp_path: Path) -> None:
    _make_copies(tmp_path, 2)
    _index(client, tmp_path)
    victim = _exact_group(client)["members"][0]["photo"]["id"]  # type: ignore[index]
    client.post("/api/quarantine", json={"photo_ids": [victim]})
    assert _exact_group(client) is None  # dissolved

    assert client.post("/api/quarantine/restore", json={"photo_ids": [victim]}).status_code == 200

    regrouped = _exact_group(client)
    assert regrouped is not None
    assert len(regrouped["members"]) == 2
    assert victim in [m["photo"]["id"] for m in regrouped["members"]]


def test_permanent_delete_of_a_grouped_then_quarantined_photo_succeeds(
    client: TestClient, tmp_path: Path
) -> None:
    _make_copies(tmp_path, 2)
    _index(client, tmp_path)
    victim = _exact_group(client)["members"][0]["photo"]["id"]  # type: ignore[index]
    client.post("/api/quarantine", json={"photo_ids": [victim]})

    deleted = client.post("/api/quarantine/delete", json={"photo_ids": [victim], "confirm": True})

    assert deleted.status_code == 200
    assert deleted.json()["succeeded"] == 1
