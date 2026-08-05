"""Application logs must survive the terminal that produced them.

Before this, every log line went to stdout only: closing the terminal or letting
--reload restart uvicorn destroyed the entire record of what the app had done.
"""

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import logging as app_logging
from app.core.config import Settings, get_settings
from app.core.context import REQUEST_ID_HEADER
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.main import _unhandled_error_handler


@pytest.fixture
def log_dir(tmp_path: Path) -> Iterator[Path]:
    """Point root logging at a temp dir, and put the real handlers back after."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    setup_logging("INFO", tmp_path)
    yield tmp_path
    for handler in root.handlers:
        handler.close()
    root.handlers, root.level = saved_handlers, saved_level


def read_lines(log_file: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]


def test_log_lines_are_written_to_the_log_file(log_dir: Path) -> None:
    logging.getLogger("app.test").warning("scan finished with %d errors", 3)

    lines = read_lines(log_dir / "aperture.log")

    assert lines[-1]["message"] == "scan finished with 3 errors"
    assert lines[-1]["level"] == "WARNING"
    assert lines[-1]["logger"] == "app.test"


def test_a_traceback_is_written_to_the_file_not_just_the_message(log_dir: Path) -> None:
    logger = logging.getLogger("app.test")
    try:
        raise RuntimeError("dataset unreadable")
    except RuntimeError:
        logger.exception("geocoding failed")

    exception = read_lines(log_dir / "aperture.log")[-1]["exception"]

    assert isinstance(exception, str)
    assert "RuntimeError: dataset unreadable" in exception


def test_the_log_file_rotates_instead_of_growing_without_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_logging, "MAX_BYTES", 2_000)
    monkeypatch.setattr(app_logging, "BACKUP_COUNT", 2)
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    setup_logging("INFO", tmp_path)
    try:
        for index in range(200):
            logging.getLogger("app.test").info("filling the log %d", index)
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers, root.level = saved_handlers, saved_level

    written = sorted(path.name for path in tmp_path.iterdir())

    # Rotated, and the oldest generations dropped rather than kept forever.
    assert written == ["aperture.log", "aperture.log.1", "aperture.log.2"]
    assert all(path.stat().st_size < 4_000 for path in tmp_path.iterdir())


def test_no_log_file_is_created_when_the_log_dir_is_blank(tmp_path: Path) -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    setup_logging("INFO", None)
    try:
        logging.getLogger("app.test").info("stdout only")
    finally:
        root.handlers, root.level = saved_handlers, saved_level

    assert list(tmp_path.iterdir()) == []


def test_a_blank_log_dir_setting_disables_file_logging() -> None:
    # Path("") would be Path("."), dropping a log file in the working directory.
    assert Settings(log_dir="").log_dir is None
    assert Settings(log_dir="~/somewhere").log_dir == Path("~/somewhere").expanduser()


def test_the_test_suite_never_writes_to_the_real_log_directory() -> None:
    """conftest sets LOG_DIR="" before the first app import.

    It has to happen there and not later: app.db.session calls the lru_cached
    get_settings() at import time, so a assignment placed after that import
    silently has no effect and the suite appends to ~/.aperture/logs.
    """
    assert get_settings().log_dir is None


# --- request context -------------------------------------------------------


def _app_that_fails() -> FastAPI:
    application = FastAPI()
    application.add_middleware(RequestContextMiddleware)
    application.add_exception_handler(Exception, _unhandled_error_handler)

    @application.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    @application.get("/fine")
    def fine() -> dict[str, bool]:
        return {"ok": True}

    return application


def test_a_request_id_is_generated_and_returned_in_the_response_header() -> None:
    with TestClient(_app_that_fails()) as client:
        response = client.get("/fine")

    assert response.headers[REQUEST_ID_HEADER]


def test_a_client_supplied_request_id_is_propagated_not_replaced() -> None:
    with TestClient(_app_that_fails()) as client:
        response = client.get("/fine", headers={REQUEST_ID_HEADER: "trace-me-42"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-me-42"


def test_every_log_line_of_a_request_carries_its_request_id(log_dir: Path) -> None:
    with TestClient(_app_that_fails()) as client:
        client.get("/fine", headers={REQUEST_ID_HEADER: "trace-me-42"})

    request_lines = [line for line in read_lines(log_dir / "aperture.log") if "status" in line]

    assert request_lines[-1]["request_id"] == "trace-me-42"
    assert request_lines[-1]["status"] == 200
    assert request_lines[-1]["message"] == "GET /fine -> 200"
    assert isinstance(request_lines[-1]["duration_ms"], float)


def test_an_unhandled_error_is_logged_with_its_request_id(log_dir: Path) -> None:
    with TestClient(_app_that_fails(), raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={REQUEST_ID_HEADER: "trace-me-42"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}

    failures = [line for line in read_lines(log_dir / "aperture.log") if line["level"] == "ERROR"]

    assert failures, "an unhandled error must leave a log line"
    assert failures[0]["request_id"] == "trace-me-42"
    assert "RuntimeError: kaboom" in str(failures[0]["exception"])


def test_a_failed_request_still_logs_its_status(log_dir: Path) -> None:
    with TestClient(_app_that_fails(), raise_server_exceptions=False) as client:
        client.get("/boom")

    request_lines = [line for line in read_lines(log_dir / "aperture.log") if "status" in line]

    assert request_lines[-1]["status"] == 500
