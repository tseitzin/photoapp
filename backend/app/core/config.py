from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aperture:aperture@localhost:5435/aperture"
    log_level: str = "INFO"
    # Where the rotating JSON log lives. Set LOG_DIR="" to log to stdout only
    # (what the test suite does, so no test ever writes to the real log).
    log_dir: Path | None = Path("~/.aperture/logs")
    thumbnail_cache_dir: Path = Path("~/.aperture/thumbnails")
    quarantine_dir: Path = Path("~/.aperture/quarantine")
    cors_origin: str = "http://localhost:5173"
    # -1 = one process per core minus one; 0 = in-process serial (tests/debugging)
    scan_workers: int = -1
    scan_batch_size: int = 500
    # Mark scans orphaned by a crash/restart as failed on startup (off in tests).
    recover_scans_on_startup: bool = True
    # Longest-edge pixels: grid thumbnails (generated during scans) and
    # lightbox previews (generated on first request).
    thumbnail_size: int = 512
    preview_size: int = 2048
    # Max pHash Hamming distance to call two photos "visually similar".
    # Values above 7 lose the completeness guarantee of the 8-band LSH lookup.
    similar_hamming_threshold: int = 6
    # Reverse geocoding names the *nearest* known place, so a photo taken far
    # from anywhere gets a far-away name. Past this, record no place at all —
    # "Reykjavík" for a mid-Atlantic photo is worse than nothing.
    place_max_km: float = 100.0

    @field_validator("thumbnail_cache_dir", "quarantine_dir")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return value.expanduser()

    @field_validator("log_dir", mode="before")
    @classmethod
    def _blank_disables_file_logging(cls, value: object) -> object:
        # Path("") is Path("."), which would drop a log file in the CWD.
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("log_dir")
    @classmethod
    def _expand_optional_user(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
