"""Scenario runner: builds the solver, advances it, and writes frames to disk.

This module knows nothing about HTTP, databases or YAML; callers pass plain
dataclasses and receive progress through callbacks.
"""

import time
from pathlib import Path
from dataclasses import field, dataclass
from collections.abc import Callable

import numpy as np

from titan3d.core.amr import AdaptiveSolver
from titan3d.core.grid import Grid
from titan3d.core.stats import FrameStats, frame_stats
from titan3d.core.params import (
    State,
    Backend,
    FloatArray,
    FlowParams,
    FluxSource,
    PileSource,
)
from titan3d.core.solver import Solver
from titan3d.core.sources import pile_depth
from titan3d.core.numerics import velocity


class RunCancelled(Exception):
    """Raised inside the run loop when cancellation is requested."""


@dataclass
class Scenario:
    """Everything needed to run one simulation on a prepared grid.

    Attributes:
        grid: Computational grid (bed, spacing, georeference).
        params: Material and numerical parameters.
        piles: Initial paraboloid piles.
        flux_sources: Vent sources.
        t_end: Simulated duration [s].
        output_every: Output interval [s].
    """

    grid: Grid
    params: FlowParams
    piles: list[PileSource] = field(default_factory=list)
    flux_sources: list[FluxSource] = field(default_factory=list)
    t_end: float = 240.0
    output_every: float = 2.0

    def __post_init__(self) -> None:
        """Validate that the scenario releases material."""
        if not self.piles and not self.flux_sources:
            raise ValueError("A scenario needs at least one pile or flux source.")
        if self.t_end <= 0 or self.output_every <= 0:
            raise ValueError("t_end and output_every must be positive.")

    @property
    def reference_point(self) -> tuple[float, float]:
        """Point runout is measured from: the first pile, else the first vent."""
        src = self.piles[0] if self.piles else self.flux_sources[0]
        return src.x, src.y

    @property
    def n_frames(self) -> int:
        """Number of output frames including ``t = 0``."""
        ratio = self.t_end / self.output_every
        full = int(np.floor(ratio + 1e-9))
        return full + 1 + (0 if ratio - full < 1e-9 else 1)


@dataclass(frozen=True)
class Progress:
    """Snapshot reported to the progress callback.

    Attributes:
        sim_t: Simulated time [s].
        t_end: Target time [s].
        steps: Completed steps.
        elapsed_s: Wall-clock time so far [s].
        eta_s: Naive remaining-time estimate [s] (``None`` before any progress).
        frames: Frames written so far.
        latest: Statistics of the most recent frame.
    """

    sim_t: float
    t_end: float
    steps: int
    elapsed_s: float
    eta_s: float | None
    frames: int
    latest: FrameStats | None

    @property
    def fraction(self) -> float:
        """Completed fraction of simulated time."""
        return min(self.sim_t / self.t_end, 1.0) if self.t_end > 0 else 1.0


@dataclass
class RunResult:
    """Outcome of :func:`run_scenario`.

    Attributes:
        stats: Per-frame statistics.
        frames_dir: Directory of ``NNNN.npz`` frames (``h``, ``speed``; float32).
        h_max: Per-cell maximum depth over every step [m].
        u_max: Per-cell maximum speed over every step [m/s].
        initial_volume: Volume of the initial piles [m³].
        wall_time_s: Wall-clock duration [s].
        backend: Backend actually used.
    """

    stats: list[FrameStats]
    frames_dir: Path
    h_max: FloatArray
    u_max: FloatArray
    initial_volume: float
    wall_time_s: float
    backend: Backend

    def load_frame(self, k: int) -> tuple[FloatArray, FloatArray]:
        """Load frame ``k`` as ``(h, speed)``."""
        with np.load(self.frames_dir / f"{k:04d}.npz") as z:
            return z["h"], z["speed"]


def run_scenario(
    scenario: Scenario,
    out_dir: Path,
    on_progress: Callable[[Progress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    progress_interval_s: float = 2.0,
) -> RunResult:
    """Run a scenario, writing one compressed frame per output time.

    Args:
        scenario: The scenario to run.
        out_dir: Run directory; frames go to ``out_dir / "frames"``.
        on_progress: Called at most every ``progress_interval_s`` and at each frame.
        should_cancel: Polled every step; returning ``True`` raises :class:`RunCancelled`.
        progress_interval_s: Minimum wall-clock spacing of progress callbacks.

    Returns:
        The run result with statistics and per-cell maxima.
    """
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    grid, p = scenario.grid, scenario.params
    solver = (AdaptiveSolver if p.amr else Solver)(grid, p, scenario.flux_sources)
    h0 = pile_depth(grid, scenario.piles)
    v0 = solver.volume(h0)
    state = solver.initial_state(h0)
    x, y = grid.x, grid.y
    stats: list[FrameStats] = []
    t_start = time.perf_counter()
    last_report = -np.inf

    def report(s: State, force: bool = False) -> None:
        nonlocal last_report
        now = time.perf_counter()
        if on_progress is None or (
            not force and now - last_report < progress_interval_s
        ):
            return
        last_report = now
        elapsed = now - t_start
        eta = elapsed / s.t * (scenario.t_end - s.t) if s.t > 0 else None
        on_progress(
            Progress(
                sim_t=s.t,
                t_end=scenario.t_end,
                steps=s.step,
                elapsed_s=elapsed,
                eta_s=eta,
                frames=len(stats),
                latest=stats[-1] if stats else None,
            )
        )

    def on_step(s: State) -> None:
        if should_cancel is not None and should_cancel():
            raise RunCancelled
        report(s)

    for s in solver.run(state, scenario.t_end, scenario.output_every, on_step):
        speed = velocity(s.h, np.hypot(s.hu, s.hv), p.h_dry)
        np.savez_compressed(
            frames_dir / f"{len(stats):04d}.npz",
            h=s.h.astype(np.float32),
            speed=speed.astype(np.float32),
        )
        stats.append(
            frame_stats(s, grid.dx, x, y, scenario.reference_point, v0, p.h_dry)
        )
        report(s, force=True)

    return RunResult(
        stats=stats,
        frames_dir=frames_dir,
        h_max=solver.h_max,
        u_max=solver.u_max,
        initial_volume=v0,
        wall_time_s=time.perf_counter() - t_start,
        backend=solver.backend,
    )
