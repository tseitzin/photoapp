from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aperture:aperture@localhost:5435/aperture"
    log_level: str = "INFO"
    thumbnail_cache_dir: Path = Path("~/.aperture/thumbnails")
    quarantine_dir: Path = Path("~/.aperture/quarantine")
    cors_origin: str = "http://localhost:5173"
    # -1 = one process per core minus one; 0 = in-process serial (tests/debugging)
    scan_workers: int = -1
    scan_batch_size: int = 500
    # Mark scans orphaned by a crash/restart as failed on startup (off in tests).
    recover_scans_on_startup: bool = True

    @field_validator("thumbnail_cache_dir", "quarantine_dir")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return value.expanduser()


@lru_cache
def get_settings() -> Settings:
    return Settings()
