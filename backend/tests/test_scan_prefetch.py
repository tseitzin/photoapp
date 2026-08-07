"""Reading ahead of the pool is an optimisation, so it must be invisible.

The prefetcher only warms the OS page cache: it changes when bytes are read,
never what is indexed. These tests pin that — the results are identical with it
on and off, an unreadable file is left for the pool to report rather than
raising on the reader thread, and the lookahead bound actually bounds.
"""

import threading
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.scans import _prefetch
from tests.images import make_image


def test_reading_ahead_stops_at_the_lookahead_bound(tmp_path: Path) -> None:
    """Unbounded, a large batch would evict the pages it just loaded before any
    worker reached them. The semaphore is what stops that.

    Asserted by the reader still being alive: with three permits and no consumer
    returning any, it must be blocked partway through rather than finished.
    """
    paths = [str(make_image(tmp_path / f"{i}.jpg")) for i in range(30)]
    done = threading.Semaphore(3)
    stop = threading.Event()

    thread = threading.Thread(target=_prefetch, args=(paths, done, stop), daemon=True)
    thread.start()
    thread.join(timeout=1.5)  # ample time to read 30 tiny files if unbounded
    still_reading = thread.is_alive()
    stop.set()
    thread.join(timeout=3)

    assert still_reading, "the reader ran past its lookahead instead of waiting"
    assert not thread.is_alive()


def test_an_unreadable_file_does_not_break_the_reader() -> None:
    """The pool reports read failures with the path and error; the prefetcher is
    a warm-up and must stay silent rather than kill its thread."""
    done = threading.Semaphore(10)
    stop = threading.Event()

    _prefetch(["/nonexistent/missing.jpg", "/nonexistent/also-missing.jpg"], done, stop)
    # Returning at all is the assertion: an OSError would have propagated.


def test_setting_the_stop_event_ends_the_reader() -> None:
    """A batch that fails mid-flight must not leave a thread reading the disk."""
    done = threading.Semaphore(0)  # no permits: the reader blocks immediately
    stop = threading.Event()
    thread = threading.Thread(target=_prefetch, args=(["/nonexistent/a.jpg"], done, stop))
    thread.start()

    stop.set()
    thread.join(timeout=3)

    assert not thread.is_alive()


def test_a_scan_indexes_the_same_photos_with_prefetch_off(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """SCAN_PREFETCH=0 is the escape hatch; it must still index everything."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "scan_prefetch", 0)
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        make_image(tmp_path / name)

    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202

    assert client.get("/api/stats").json()["photos"] == 3


def test_a_scan_indexes_the_same_photos_with_prefetch_on(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "scan_prefetch", 64)
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        make_image(tmp_path / name)

    assert client.post("/api/scan-roots", json={"path": str(tmp_path)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202

    assert client.get("/api/stats").json()["photos"] == 3
