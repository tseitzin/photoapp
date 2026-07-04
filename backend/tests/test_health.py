from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


class _RespondingSession:
    def execute(self, *args: Any, **kwargs: Any) -> None:
        return None


class _UnreachableSession:
    def execute(self, *args: Any, **kwargs: Any) -> None:
        raise OperationalError("SELECT 1", None, Exception("connection refused"))


def _override(session: Any) -> None:
    def _get_db() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_db] = _get_db


def test_health_reports_ok_when_database_responds(client: TestClient) -> None:
    _override(_RespondingSession())

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"]


def test_health_still_answers_and_flags_database_when_db_is_unreachable(
    client: TestClient,
) -> None:
    _override(_UnreachableSession())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["database"] == "unavailable"
