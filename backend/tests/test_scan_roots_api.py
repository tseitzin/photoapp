from pathlib import Path

from fastapi.testclient import TestClient


def _create(client: TestClient, path: Path) -> dict:
    response = client.post("/api/scan-roots", json={"path": str(path)})
    assert response.status_code == 201, response.text
    return response.json()


def test_created_root_is_returned_and_listed(client: TestClient, tmp_path: Path) -> None:
    created = _create(client, tmp_path)

    assert created["path"] == str(tmp_path.resolve())
    assert created["enabled"] is True

    listed = client.get("/api/scan-roots").json()
    assert [r["id"] for r in listed] == [created["id"]]


def test_rejects_relative_path(client: TestClient) -> None:
    response = client.post("/api/scan-roots", json={"path": "Pictures/photos"})

    assert response.status_code == 422
    assert "absolute" in response.json()["detail"]


def test_rejects_path_that_is_not_an_existing_directory(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/scan-roots", json={"path": str(tmp_path / "nope")})

    assert response.status_code == 422


def test_rejects_duplicate_root(client: TestClient, tmp_path: Path) -> None:
    _create(client, tmp_path)

    response = client.post("/api/scan-roots", json={"path": str(tmp_path)})

    assert response.status_code == 409


def test_rejects_root_nested_inside_an_existing_root(client: TestClient, tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    _create(client, tmp_path)

    response = client.post("/api/scan-roots", json={"path": str(child)})

    assert response.status_code == 409
    assert "inside" in response.json()["detail"]


def test_rejects_root_that_contains_an_existing_root(client: TestClient, tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    _create(client, child)

    response = client.post("/api/scan-roots", json={"path": str(tmp_path)})

    assert response.status_code == 409
    assert "contains" in response.json()["detail"]


def test_disabling_a_root_persists(client: TestClient, tmp_path: Path) -> None:
    created = _create(client, tmp_path)

    patched = client.patch(f"/api/scan-roots/{created['id']}", json={"enabled": False})

    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    assert client.get("/api/scan-roots").json()[0]["enabled"] is False


def test_deleting_a_root_removes_it(client: TestClient, tmp_path: Path) -> None:
    created = _create(client, tmp_path)

    assert client.delete(f"/api/scan-roots/{created['id']}").status_code == 204
    assert client.get("/api/scan-roots").json() == []


def test_unknown_root_returns_404(client: TestClient) -> None:
    assert client.delete("/api/scan-roots/9999").status_code == 404
    assert client.patch("/api/scan-roots/9999", json={"enabled": True}).status_code == 404
