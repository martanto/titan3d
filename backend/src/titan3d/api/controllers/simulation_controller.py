"""Simulation jobs: submit, inspect, cancel, duplicate, download."""

import uuid
import shutil
from pathlib import Path

from titan3d.config import Settings
from titan3d.core.dem import DemError, load_domain, lonlat_to_xy
from titan3d.api.errors import Conflict, NotFound, Unprocessable
from titan3d.db.repositories import JobRecord, JobRepository
from titan3d.api.workers.runner import build_bundle
from titan3d.api.schemas.scenario import ScenarioRequest
from titan3d.api.schemas.simulation import (
    GridOut,
    ProgressOut,
    RuntimeClass,
    FrameStatsOut,
    SimulationOut,
    ScenarioEstimate,
    SimulationCreated,
)
from titan3d.api.workers.dispatcher import Dispatcher
from titan3d.api.controllers.dem_controller import DemController


ARTIFACTS = {
    "max_depth.tif": "image/tiff",
    "max_speed.tif": "image/tiff",
    "inundation.geojson": "application/geo+json",
    "inundation.kml": "application/vnd.google-earth.kml+xml",
    "scenario.yaml": "application/x-yaml",
    "summary.json": "application/json",
    "run.log": "text/plain",
}

# Throughput of the Numba backend measured on the development machine
# (cell-steps per second) and the share of the domain typically active.
_CELL_STEPS_PER_S = {"numba": 6.0e6, "numpy": 0.5e6}
_ACTIVE_FRACTION = 0.3
_TYPICAL_SPEED = 60.0  # m/s, for the time-step estimate


def estimate(req: ScenarioRequest) -> ScenarioEstimate:
    """Rough cost of a scenario (grid size, memory, runtime class)."""
    ny, nx = req.grid_shape()
    cells = ny * nx
    n = req.numerics
    dt = n.cfl * n.dx / _TYPICAL_SPEED
    steps = req.t_end / dt
    rate = _CELL_STEPS_PER_S[n.backend.value]
    seconds = cells * _ACTIVE_FRACTION * steps / rate
    cls: RuntimeClass = (
        "seconds"
        if seconds < 60
        else "minutes"
        if seconds < 600
        else "tens of minutes"
        if seconds < 3600
        else "hours"
    )
    bytes_per = 4 if n.precision.value == "float32" else 8
    return ScenarioEstimate(
        grid_shape=(ny, nx),
        cells=cells,
        memory_mb=round(cells * bytes_per * 16 / 1e6, 1),
        released_m3=req.released_volume_m3(),
        frames=int(req.t_end / req.output_every) + 1,
        runtime_class=cls,
    )


class SimulationController:
    """Business logic for simulation endpoints."""

    def __init__(self, settings: Settings, dems: DemController, dispatcher: Dispatcher):
        self.settings = settings
        self.dems = dems
        self.dispatcher = dispatcher
        self.repo = JobRepository(settings.db_path)

    # ------------------------------------------------------------ mapping
    def run_dir(self, job_id: str) -> Path:
        """Artifact directory of a job."""
        return self.settings.runs_dir / job_id

    def to_out(self, rec: JobRecord) -> SimulationOut:
        """Response model for a job record."""
        d = self.run_dir(rec.id)
        artifacts = (
            [n for n in ARTIFACTS if (d / n).exists()] if rec.status != "queued" else []
        )
        return SimulationOut(
            id=rec.id,
            name=rec.name,
            dem_id=rec.dem_id,
            status=rec.status,
            scenario=ScenarioRequest.model_validate(rec.scenario),
            progress=ProgressOut(
                fraction=rec.progress,
                sim_t=rec.sim_t,
                t_end=rec.t_end,
                steps=rec.steps,
                frames=rec.frames,
                elapsed_s=rec.elapsed_s,
                eta_s=rec.eta_s,
                hmax=rec.hmax,
                umax=rec.umax,
                runout=rec.runout,
                area=rec.area,
                vol_in_domain=rec.vol_in_domain,
                vol_out=rec.vol_out,
                released_m3=rec.released_m3,
            ),
            provenance=rec.provenance,
            grid=GridOut.model_validate(rec.grid) if rec.grid else None,
            parent_job_id=rec.parent_job_id,
            created_at=rec.created_at,
            started_at=rec.started_at,
            finished_at=rec.finished_at,
            error=rec.error,
            cancel_requested=rec.cancel_requested,
            artifacts=artifacts,
        )

    def record(self, job_id: str) -> JobRecord:
        """Job or :class:`NotFound`."""
        rec = self.repo.get(job_id)
        if rec is None:
            raise NotFound(f"Simulation '{job_id}' not found.")
        return rec

    # ------------------------------------------------------------ queries
    def list_recent(self, limit: int = 200) -> list[SimulationOut]:
        """Recent simulations."""
        return [self.to_out(r) for r in self.repo.list_recent(limit)]

    def get(self, job_id: str) -> SimulationOut:
        """One simulation with progress."""
        return self.to_out(self.record(job_id))

    def frames(self, job_id: str) -> list[FrameStatsOut]:
        """Per-frame statistics recorded so far."""
        self.record(job_id)
        return [FrameStatsOut.model_validate(s) for s in self.repo.frames(job_id)]

    # ------------------------------------------------------------ commands
    def validate_domain(self, req: ScenarioRequest) -> None:
        """Check DEM coverage on a coarse grid so bad domains fail at submit time."""
        rec = self.dems.ready(req.dem_id)
        d = req.domain
        coarse = max(
            (d.west_km + d.east_km) * 1000 / 96, (d.south_km + d.north_km) * 1000 / 96
        )
        try:
            grid = load_domain(
                Path(rec.mosaic_path or ""),
                req.anchor,
                (d.west_km, d.east_km, d.south_km, d.north_km),
                max(coarse, req.numerics.dx),
            )
        except DemError as exc:
            raise Unprocessable(str(exc)) from exc
        sources = [("Pile", p.lon, p.lat) for p in req.piles]
        sources += [("Flux source", f.lon, f.lat) for f in req.flux_sources]
        for k, (what, lon, lat) in enumerate(sources):
            x, y = lonlat_to_xy(grid.crs or "", lon, lat)
            if not grid.contains(x, y):
                raise Unprocessable(
                    f"{what} {k + 1} at ({lon:.5f}, {lat:.5f}) lies outside the domain."
                )

    def create(
        self, req: ScenarioRequest, parent_job_id: str | None = None
    ) -> SimulationCreated:
        """Validate and queue a simulation."""
        self.validate_domain(req)
        job_id = uuid.uuid4().hex[:12]
        rec = self.repo.create(
            job_id,
            req.name,
            req.dem_id,
            req.model_dump(mode="json"),
            req.t_end,
            parent_job_id,
        )
        self.dispatcher.wake()
        ny, nx = req.grid_shape()
        return SimulationCreated(
            id=rec.id,
            status=rec.status,
            estimated_cells=ny * nx,
            grid_shape=(ny, nx),
        )

    def duplicate(self, job_id: str) -> SimulationCreated:
        """Queue a new run with the same scenario."""
        rec = self.record(job_id)
        req = ScenarioRequest.model_validate(rec.scenario)
        return self.create(req, parent_job_id=rec.id)

    def cancel(self, job_id: str) -> SimulationOut:
        """Cancel a queued job or ask a running one to stop."""
        self.record(job_id)
        self.repo.request_cancel(job_id)
        return self.get(job_id)

    def delete(self, job_id: str) -> None:
        """Delete a job and its artifacts (stopping it first if running)."""
        rec = self.record(job_id)
        if rec.status in ("queued", "running"):
            self.repo.request_cancel(job_id)
            self.dispatcher.kill(job_id)
            self.repo.finish(job_id, "cancelled", "Deleted while running")
        self.repo.delete(job_id)
        shutil.rmtree(self.run_dir(job_id), ignore_errors=True)

    # ----------------------------------------------------------- downloads
    def result_path(self, job_id: str, max_cells: int) -> Path:
        """Viewer bundle of a completed run (built on demand per detail level)."""
        rec = self.record(job_id)
        if rec.status != "completed":
            raise Conflict(
                f"Simulation is {rec.status}; results exist only when completed."
            )
        return build_bundle(self.run_dir(job_id), max_cells)

    def artifact_path(self, job_id: str, name: str) -> tuple[Path, str]:
        """Path and media type of a downloadable artifact."""
        self.record(job_id)
        if name not in ARTIFACTS:
            raise NotFound(f"Unknown artifact '{name}'.")
        p = self.run_dir(job_id) / name
        if not p.exists():
            raise NotFound(f"'{name}' is not available for this simulation.")
        return p, ARTIFACTS[name]
