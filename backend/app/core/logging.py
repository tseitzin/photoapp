import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.context import get_request_id

LOG_FILENAME = "aperture.log"
# 10 MB per file, 5 kept: a ~60 MB ceiling for the whole log directory, which is
# weeks of a single-user app and small enough to read with jq.
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

# Structured fields a caller may attach with `extra=`; anything else is ignored
# so a stray keyword can never change the shape of a log line.
_EXTRA_FIELDS = ("duration_ms", "status")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def log_file_path(log_dir: Path) -> Path:
    return log_dir / LOG_FILENAME


def setup_logging(level: str, log_dir: Path | None = None) -> None:
    """Send JSON logs to stdout, and to a rotating file when log_dir is set.

    Without the file handler every log line lives only in the terminal running
    uvicorn and is gone when it closes — which is no record at all.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir is not None:
        # The app creates its own log directory and rotation only ever replaces
        # its own aperture.log.N files. Nothing else on disk is touched.
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_file_path(log_dir),
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
        )

    formatter = JsonFormatter()
    for handler in handlers:
        handler.setFormatter(formatter)

    root = logging.getLogger()
    # Close what we are replacing, or repeated setup leaks open file handles.
    for previous in root.handlers:
        previous.close()
    root.handlers = handlers
    root.setLevel(level.upper())
    # uvicorn installs its own handlers; route everything through ours instead
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
