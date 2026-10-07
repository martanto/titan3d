"""Application settings, read from ``TITAN3D_*`` environment variables or ``.env``."""

from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Runtime configuration for the API, worker and CLI."""

    model_config = SettingsConfigDict(
        env_prefix="TITAN3D_", env_file=".env", extra="ignore"
    )

    data_dir: Path = Field(
        default=_REPO_ROOT / "data",
        description="Root for the SQLite DB, uploaded DEMs, run artifacts and logs.",
    )
    builtin_dem_dir: Path = Field(
        default=_REPO_ROOT / "dem",
        description="Directory of GeoTIFF tiles registered as the built-in DEM.",
    )
    builtin_dem_id: str = "semeru"
    builtin_dem_name: str = "Semeru — DEMNAS 0.27″"
    max_concurrent_runs: int = Field(default=1, ge=1)
    max_upload_file_mb: int = Field(default=1024, ge=1)
    max_upload_files: int = Field(default=64, ge=1)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    frontend_dist: Path = Field(
        default=_REPO_ROOT / "frontend" / "dist",
        description="Built frontend served at '/' by FastAPI (skipped if missing).",
    )
    basic_auth_user: str | None = Field(
        default=None,
        description="Enable HTTP basic auth when user and password are set.",
    )
    basic_auth_password: str | None = None
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def db_path(self) -> Path:
        """Path of the SQLite database file."""
        return self.data_dir / "titan3d.db"

    @property
    def dems_dir(self) -> Path:
        """Directory holding one sub-directory per registered DEM."""
        return self.data_dir / "dems"

    @property
    def runs_dir(self) -> Path:
        """Directory holding one sub-directory of artifacts per simulation."""
        return self.data_dir / "runs"

    @property
    def logs_dir(self) -> Path:
        """Directory for rotating log files."""
        return self.data_dir / "logs"

    @property
    def basic_auth_enabled(self) -> bool:
        """Whether HTTP basic auth protects the API and UI."""
        return bool(self.basic_auth_user and self.basic_auth_password)

    def ensure_dirs(self) -> None:
        """Create the data directories if they do not exist."""
        for d in (self.data_dir, self.dems_dir, self.runs_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
