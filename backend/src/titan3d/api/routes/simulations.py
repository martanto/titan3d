"""Simulation endpoints: submit, list, progress, cancel, duplicate, downloads."""

from typing import Literal, Annotated

from fastapi import Query, Response, APIRouter, status
from fastapi.responses import FileResponse

from titan3d.api.deps import SimulationsDep
from titan3d.api.schemas.scenario import ScenarioRequest
from titan3d.api.schemas.simulation import (
    FrameStatsOut,
    SimulationOut,
    SimulationCreated,
)


router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a simulation",
    responses={409: {"description": "DEM not ready"}, 422: {"description": "Invalid"}},
)
def create_simulation(req: ScenarioRequest, sims: SimulationsDep) -> SimulationCreated:
    """Validate the scenario against the DEM and queue it."""
    return sims.create(req)


@router.get("", summary="List simulations")
def list_simulations(
    sims: SimulationsDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200
) -> list[SimulationOut]:
    """Most recent simulations first."""
    return sims.list_recent(limit)


@router.get("/{job_id}", summary="Simulation status and progress")
def get_simulation(job_id: str, sims: SimulationsDep) -> SimulationOut:
    """Status, live progress, provenance and available artifacts."""
    return sims.get(job_id)


@router.get("/{job_id}/frames", summary="Per-frame statistics so far")
def get_frames(job_id: str, sims: SimulationsDep) -> list[FrameStatsOut]:
    """Frame statistics recorded so far (for live sparklines)."""
    return sims.frames(job_id)


@router.post("/{job_id}/cancel", summary="Cancel a simulation")
def cancel_simulation(job_id: str, sims: SimulationsDep) -> SimulationOut:
    """Cancel a queued job, or ask a running one to stop (within about a second)."""
    return sims.cancel(job_id)


@router.post(
    "/{job_id}/duplicate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run the same scenario again",
)
def duplicate_simulation(job_id: str, sims: SimulationsDep) -> SimulationCreated:
    """Queue a new simulation with an identical scenario."""
    return sims.duplicate(job_id)


@router.delete(
    "/{job_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a simulation"
)
def delete_simulation(job_id: str, sims: SimulationsDep) -> Response:
    """Delete a simulation and its artifacts (stops it if running)."""
    sims.delete(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{job_id}/result",
    summary="Viewer bundle (gzipped JSON)",
    response_class=FileResponse,
    responses={200: {"content": {"application/json": {}}}},
)
def get_result(
    job_id: str,
    sims: SimulationsDep,
    max_cells: Annotated[
        int, Query(ge=128, le=1600, description="Viewer detail: max cells per side")
    ] = 640,
) -> FileResponse:
    """Quantised frames for 3D playback (full-resolution data is in the GeoTIFFs)."""
    path = sims.result_path(job_id, max_cells)
    return FileResponse(
        path, media_type="application/json", headers={"Content-Encoding": "gzip"}
    )


Artifact = Literal[
    "max_depth.tif",
    "max_speed.tif",
    "inundation.geojson",
    "inundation.kml",
    "scenario.yaml",
    "summary.json",
    "run.log",
]


@router.get(
    "/{job_id}/files/{name}",
    summary="Download an artifact",
    response_class=FileResponse,
)
def get_artifact(job_id: str, name: Artifact, sims: SimulationsDep) -> FileResponse:
    """GeoTIFF maxima, inundation outline, scenario YAML, summary or log."""
    path, media = sims.artifact_path(job_id, name)
    return FileResponse(path, media_type=media, filename=f"{job_id}_{name}")
