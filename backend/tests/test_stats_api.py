from pathlib import Path

from fastapi.testclient import TestClient

from tests.images import make_image


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def test_stats_reflect_indexed_library(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "a.jpg", color="coral")
    make_image(tmp_path / "2024/b.jpg", color="navy")
    _index(client, tmp_path)

    stats = client.get("/api/stats").json()

    assert stats["photos"] == 2
    assert stats["storage_bytes"] > 0
    assert stats["folders"] == 2
    assert stats["duplicate_photos"] == 0
    assert stats["last_scan_at"] is not None


def test_stats_count_exact_duplicates_and_reclaimable_bytes(
    client: TestClient, tmp_path: Path
) -> None:
    original = make_image(tmp_path / "orig.jpg", color="crimson")
    (tmp_path / "copy1.jpg").write_bytes(original.read_bytes())
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/copy2.jpg").write_bytes(original.read_bytes())
    make_image(tmp_path / "unique.jpg", color="lime")
    _index(client, tmp_path)

    stats = client.get("/api/stats").json()

    assert stats["photos"] == 4
    # 3 identical copies -> 2 redundant
    assert stats["duplicate_photos"] == 2
    assert stats["reclaimable_bytes"] == 2 * original.stat().st_size


def test_stats_on_empty_library(client: TestClient) -> None:
    stats = client.get("/api/stats").json()

    assert stats["photos"] == 0
    assert stats["storage_bytes"] == 0
    assert stats["duplicate_photos"] == 0
    assert stats["last_scan_at"] is None
