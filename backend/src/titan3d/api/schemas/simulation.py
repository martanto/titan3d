"""Simulation (job) response models."""

from typing import Any, Literal

from pydantic import Field, BaseModel

from titan3d.api.schemas.scenario import ScenarioRequest


JobStatus = Literal[
    "queued", "running", "completed", "failed", "cancelled", "interrupted"
]


class GridOut(BaseModel):
    """Computational grid of a run."""

    nx: int
    ny: int
    dx: float
    x0: float
    y0: float
    crs: str | None
    bounds: list[float]
    bounds_lonlat: list[float] | None
    zmin: float
    zmax: float


class ProgressOut(BaseModel):
    """Live progress of a run."""

    fraction: float = Field(description="Completed fraction of simulated time (0–1)")
    sim_t: float = Field(description="Simulated time [s]")
    t_end: float
    steps: int
    frames: int
    elapsed_s: float
    eta_s: float | None
    hmax: float | None = Field(None, description="Max depth in the latest frame [m]")
    umax: float | None = Field(None, description="Max speed in the latest frame [m/s]")
    runout: float | None = Field(None, description="Runout in the latest frame [m]")
    area: float | None = Field(None, description="Inundated area [km²]")
    vol_in_domain: float | None = Field(None, description="Fraction of released volume")
    vol_out: float | None = Field(None, description="Fraction that left the domain")
    released_m3: float | None = None


class SimulationOut(BaseModel):
    """A simulation job."""

    id: str
    name: str
    dem_id: str
    status: JobStatus
    scenario: ScenarioRequest
    progress: ProgressOut
    provenance: dict[str, Any] | None = None
    grid: GridOut | None = None
    parent_job_id: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    artifacts: list[str] = Field(
        default_factory=list, description="Downloadable artifact names"
    )


class FrameStatsOut(BaseModel):
    """Statistics of one output frame."""

    t: float
    steps: int
    vol: float
    vol_out: float
    released_m3: float
    hmax: float
    umax: float
    area: float
    runout: float


class SimulationCreated(BaseModel):
    """Response to a submitted simulation."""

    id: str
    status: JobStatus
    estimated_cells: int
    grid_shape: tuple[int, int]


RuntimeClass = Literal["seconds", "minutes", "tens of minutes", "hours"]


class ScenarioEstimate(BaseModel):
    """Cost estimate for a scenario before running it."""

    grid_shape: tuple[int, int]
    cells: int
    memory_mb: float = Field(description="Approximate peak memory of the solver [MB]")
    released_m3: float
    frames: int
    runtime_class: RuntimeClass


class ImportErrorItem(BaseModel):
    """One field-level validation problem in an imported config."""

    loc: str
    msg: str


class ScenarioImportOut(BaseModel):
    """Result of importing a YAML config."""

    ok: bool
    scenario: ScenarioRequest | None = None
    errors: list[ImportErrorItem] = Field(default_factory=list)


class MessageOut(BaseModel):
    """Simple status message."""

    detail: str
