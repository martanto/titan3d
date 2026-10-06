"""System health endpoints."""

from typing import Annotated

from fastapi import Query, APIRouter

from titan3d.api.deps import SystemDep
from titan3d.api.schemas.system import SystemOut, CacheClearOut


router = APIRouter(prefix="/system", tags=["system"])


@router.get("", summary="Server resources, services and storage")
def system_health(
    system: SystemDep,
    refresh: Annotated[
        bool, Query(description="Measure now instead of reusing the last reading")
    ] = False,
) -> SystemOut:
    """Disk, memory and CPU usage, service health and storage, cached briefly."""
    return system.snapshot(refresh)


@router.post("/caches/clear", summary="Clear regenerable caches")
def clear_caches(system: SystemDep) -> CacheClearOut:
    """Delete terrain previews and playback bundles; they are rebuilt on the next request."""
    return system.clear_caches()
