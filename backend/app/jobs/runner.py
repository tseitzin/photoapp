"""Minimal background-job runner.

v1 is a single worker thread inside the API process. Job state lives in the
database (the Scan row), workers are plain functions taking ids — the same
shape a real queue (Celery/RQ/arq) expects, so swapping the runner later is a
wiring change, not a rewrite.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

logger = logging.getLogger(__name__)


class JobRunner(Protocol):
    def submit(self, name: str, fn: Callable[[], None]) -> None: ...


class ThreadJobRunner:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aperture-job")

    def submit(self, name: str, fn: Callable[[], None]) -> None:
        logger.info("job submitted: %s", name)
        self._executor.submit(self._run, name, fn)

    @staticmethod
    def _run(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
            logger.info("job finished: %s", name)
        except Exception:
            # The job itself persists failure state; this is the last-resort log.
            logger.exception("job crashed: %s", name)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class InlineJobRunner:
    """Runs jobs synchronously — used by tests for deterministic scans."""

    def submit(self, name: str, fn: Callable[[], None]) -> None:
        fn()


_runner: ThreadJobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = ThreadJobRunner()
    return _runner
