"""Health check."""

from fastapi import APIRouter
from pydantic import BaseModel

from titan3d.version import git_commit, package_version
from titan3d.api.deps import SettingsDep


router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    """Service status."""

    status: str
    version: str
    commit: str
    max_concurrent_runs: int


@router.get("/health", summary="Service health and version")
def health(settings: SettingsDep) -> HealthOut:
    """Return service status and version."""
    return HealthOut(
        status="ok",
        version=package_version(),
        commit=git_commit(),
        max_concurrent_runs=settings.max_concurrent_runs,
    )
