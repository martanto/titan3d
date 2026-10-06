"""Run execution shared by the background worker and the CLI.

``execute_run`` turns a validated :class:`ScenarioRequest` into a core
:class:`~titan3d.core.scenario.Scenario`, runs it, and writes all artifacts.
``worker_main`` is the child-process entry point that wires progress and
cancellation to SQLite.
"""

import sys
import json
import time
import platform
import traceback
from typing import Any
from pathlib import Path
from collections.abc import Callable

import numpy as np
from loguru import logger

from titan3d.version import git_commit, package_version
from titan3d.core.dem import DemError, load_domain, lonlat_to_xy, xy_to_lonlat
from titan3d.core.grid import Grid
from titan3d.core.export import (
    viewer_bundle,
    write_geotiff,
    write_json_gz,
    geojson_to_kml,
    inundation_geojson,
)
from titan3d.core.params import FlowParams, FluxSource, PileSource
from titan3d.core.scenario import (
    Progress,
    Scenario,
    RunResult,
    RunCancelled,
    run_scenario,
)
from titan3d.api.schemas.scenario import ScenarioRequest
from titan3d.api.schemas.scenario_yaml import scenario_to_yaml


DEFAULT_VIEW_CELLS = 640
INUNDATION_THRESHOLD_M = 0.1


def provenance(req: ScenarioRequest, dem_info: dict[str, Any] | None) -> dict[str, Any]:
    """Versions and inputs that identify how a run was produced."""
    import numba
    import rasterio

    return {
        "titan3d_version": package_version(),
        "git_commit": git_commit(),
        "dem_id": req.dem_id,
        "dem_sha256": (dem_info or {}).get("sha256"),
        "backend": req.numerics.backend.value,
        "precision": req.numerics.precision.value,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "numba": numba.__version__,
        "rasterio": rasterio.__version__,
        "platform": platform.platform(),
    }


def build_scenario(req: ScenarioRequest, mosaic: Path) -> Scenario:
    """Cut the domain from the mosaic and place sources in grid coordinates.

    Raises:
        DemError: If the domain leaves DEM coverage or a source lies outside it.
    """
    d = req.domain
    grid = load_domain(
        mosaic,
        req.anchor,
        (d.west_km, d.east_km, d.south_km, d.north_km),
        req.numerics.dx,
    )
    crs = grid.crs or ""

    def place(lon: float, lat: float, what: str) -> tuple[float, float]:
        x, y = lonlat_to_xy(crs, lon, lat)
        if not grid.contains(x, y):
            raise DemError(f"{what} at ({lon:.5f}, {lat:.5f}) lies outside the domain.")
        return x, y

    piles = []
    for k, p in enumerate(req.piles):
        x, y = place(p.lon, p.lat, f"Pile {k + 1}")
        piles.append(PileSource(x=x, y=y, height=p.height, radius=p.radius))
    fluxes = []
    for k, f in enumerate(req.flux_sources):
        x, y = place(f.lon, f.lat, f"Flux source {k + 1}")
        fluxes.append(
            FluxSource(
                x=x,
                y=y,
                radius=f.radius,
                influx=f.influx,
                start=f.start,
                duration=f.duration,
                speed=f.speed,
                direction_deg=f.direction_deg,
            )
        )
    m, n = req.material, req.numerics
    params = FlowParams(
        rheology=m.rheology,
        phi_bed_deg=m.phi_bed_deg,
        phi_int_deg=m.phi_int_deg,
        mu=m.mu,
        xi=m.xi,
        earth_pressure=m.earth_pressure,
        curvature=m.curvature,
        cfl=n.cfl,
        h_dry=n.h_dry,
        precision=n.precision,
        backend=n.backend,
    )
    return Scenario(
        grid=grid,
        params=params,
        piles=piles,
        flux_sources=fluxes,
        t_end=req.t_end,
        output_every=req.output_every,
    )


def grid_summary(grid: Grid) -> dict[str, Any]:
    """JSON description of a computational grid."""
    w, s, e, n = grid.bounds
    corners = (
        [xy_to_lonlat(grid.crs, x, y) for x, y in ((w, s), (e, n))] if grid.crs else []
    )
    return {
        "nx": grid.nx,
        "ny": grid.ny,
        "dx": grid.dx,
        "x0": grid.x0,
        "y0": grid.y0,
        "crs": grid.crs,
        "bounds": [w, s, e, n],
        "bounds_lonlat": [*corners[0], *corners[1]] if corners else None,
        "zmin": float(np.min(grid.b)),
        "zmax": float(np.max(grid.b)),
    }


def _bundle_meta(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))


def build_bundle(run_dir: Path, max_cells: int = DEFAULT_VIEW_CELLS) -> Path:
    """(Re)build the viewer bundle for a finished run at a given detail level."""
    out = run_dir / f"bundle_{max_cells}.json.gz"
    if out.exists():
        return out
    with np.load(run_dir / "grid.npz") as z:
        crs = str(z["crs"]) or None
        grid = Grid(
            b=z["b"], dx=float(z["dx"]), x0=float(z["x0"]), y0=float(z["y0"]), crs=crs
        )
    with np.load(run_dir / "maxima.npz") as z:
        h_max = z["h_max"]
    from titan3d.core.stats import FrameStats

    stats = [
        FrameStats(**s)
        for s in json.loads((run_dir / "stats.json").read_text(encoding="utf-8"))
    ]

    def load(k: int) -> tuple[np.ndarray, np.ndarray]:
        with np.load(run_dir / "frames" / f"{k:04d}.npz") as z:
            return z["h"], z["speed"]

    data = viewer_bundle(grid, load, stats, h_max, _bundle_meta(run_dir), max_cells)
    tmp = out.with_suffix(".tmp")
    write_json_gz(tmp, data)
    tmp.replace(out)
    return out


def write_artifacts(
    run_dir: Path,
    req: ScenarioRequest,
    scenario: Scenario,
    result: RunResult,
    prov: dict[str, Any],
    dem_name: str,
) -> dict[str, Any]:
    """Write grid, maxima, stats, GeoTIFFs, inundation outline, YAML and bundle."""
    grid = scenario.grid
    np.savez_compressed(
        run_dir / "grid.npz",
        b=grid.b.astype(np.float32),
        dx=grid.dx,
        x0=grid.x0,
        y0=grid.y0,
        crs=np.array(grid.crs or ""),
    )
    np.savez_compressed(
        run_dir / "maxima.npz",
        h_max=result.h_max.astype(np.float32),
        u_max=result.u_max.astype(np.float32),
    )
    stats = [s.to_dict() for s in result.stats]
    (run_dir / "stats.json").write_text(json.dumps(stats), encoding="utf-8")
    (run_dir / "scenario.yaml").write_text(scenario_to_yaml(req), encoding="utf-8")
    write_geotiff(run_dir / "max_depth.tif", result.h_max, grid)
    write_geotiff(run_dir / "max_speed.tif", result.u_max, grid)
    fc = inundation_geojson(grid, result.h_max, INUNDATION_THRESHOLD_M)
    fc["properties"] |= {"scenario": req.name, "dem": dem_name}
    (run_dir / "inundation.geojson").write_text(json.dumps(fc), encoding="utf-8")
    (run_dir / "inundation.kml").write_text(
        geojson_to_kml(fc, req.name), encoding="utf-8"
    )

    ref = scenario.reference_point
    sources = [
        {
            "kind": "pile",
            "x": p.x,
            "y": p.y,
            "height": p.height,
            "radius": p.radius,
            "lon": q.lon,
            "lat": q.lat,
        }
        for p, q in zip(scenario.piles, req.piles, strict=True)
    ] + [
        {
            "kind": "flux",
            "x": f.x,
            "y": f.y,
            "radius": f.radius,
            "influx": f.influx,
            "start": f.start,
            "duration": f.duration,
            "lon": q.lon,
            "lat": q.lat,
        }
        for f, q in zip(scenario.flux_sources, req.flux_sources, strict=True)
    ]
    last = result.stats[-1]
    meta = {
        "title": req.name,
        "dem": dem_name,
        "rheology": req.material.rheology.value,
        "phi_bed": req.material.phi_bed_deg,
        "phi_int": req.material.phi_int_deg,
        "mu": req.material.mu,
        "xi": req.material.xi,
        "pressure": req.material.earth_pressure.value,
        "curvature": req.material.curvature,
        "every": req.output_every,
        "t_end": req.t_end,
        "volume_m3": last.released_m3,
        "sources": sources,
        "ref": {"x": ref[0], "y": ref[1]},
        "grid_dx": grid.dx,
        "grid_shape": [grid.ny, grid.nx],
        "steps": last.steps,
        "wall_time_s": round(result.wall_time_s, 1),
        "provenance": prov,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    build_bundle(run_dir, DEFAULT_VIEW_CELLS)
    summary = {
        "frames": len(result.stats),
        "steps": last.steps,
        "wall_time_s": result.wall_time_s,
        "hmax": float(np.max(result.h_max)),
        "umax": float(np.max(result.u_max)),
        "runout": max(s.runout for s in result.stats),
        "inundated_km2": fc["properties"]["area_km2"],
        "vol_in_domain": last.vol,
        "vol_out": last.vol_out,
        "released_m3": last.released_m3,
        "backend": result.backend.value,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def execute_run(
    req: ScenarioRequest,
    mosaic: Path,
    run_dir: Path,
    dem_info: dict[str, Any] | None = None,
    dem_name: str = "",
    on_started: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Build, run and export one scenario.

    Args:
        req: Validated scenario.
        mosaic: Stitched DEM GeoTIFF.
        run_dir: Output directory.
        dem_info: Mosaic metadata (for provenance).
        dem_name: Display name of the DEM.
        on_started: Called with ``(provenance, grid_summary)`` once the grid exists.
        on_progress: Progress callback.
        should_cancel: Cancellation poll.

    Returns:
        Run summary.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    prov = provenance(req, dem_info)
    scenario = build_scenario(req, mosaic)
    g = grid_summary(scenario.grid)
    logger.info(
        "grid {}×{} @ {} m ({}) — {} piles, {} flux sources, t_end {} s",
        g["ny"],
        g["nx"],
        g["dx"],
        g["crs"],
        len(scenario.piles),
        len(scenario.flux_sources),
        req.t_end,
    )
    if on_started is not None:
        on_started(prov, g)
    result = run_scenario(scenario, run_dir, on_progress, should_cancel)
    logger.info("solver finished in {:.1f} s; writing artifacts", result.wall_time_s)
    return write_artifacts(run_dir, req, scenario, result, prov, dem_name)


def worker_main(
    job_id: str, db_path: str, runs_dir: str, log_level: str = "INFO"
) -> None:
    """Child-process entry point: run one job and record its outcome in SQLite."""
    from titan3d.logging import setup_logging
    from titan3d.db.repositories import DemRepository, JobRepository

    run_dir = Path(runs_dir) / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(log_level, run_dir / "run.log")
    jobs, dems = JobRepository(Path(db_path)), DemRepository(Path(db_path))
    job = jobs.get(job_id)
    if job is None:
        logger.error("job {} not found", job_id)
        return
    import os

    jobs.set_pid(job_id, os.getpid())
    last_cancel_check = 0.0
    cancelled = False

    def should_cancel() -> bool:
        nonlocal last_cancel_check, cancelled
        now = time.monotonic()
        if now - last_cancel_check >= 1.0:
            last_cancel_check = now
            cancelled = jobs.cancel_requested(job_id)
        return cancelled

    frames_logged = 0

    def on_progress(p: Progress) -> None:
        nonlocal frames_logged
        values: dict[str, Any] = {
            "sim_t": p.sim_t,
            "steps": p.steps,
            "frames": p.frames,
            "elapsed_s": p.elapsed_s,
            "eta_s": p.eta_s,
        }
        if p.latest is not None:
            s = p.latest
            values |= {
                "hmax": s.hmax,
                "umax": s.umax,
                "runout": s.runout,
                "area": s.area,
                "vol_in_domain": s.vol,
                "vol_out": s.vol_out,
                "released_m3": s.released_m3,
            }
            if p.frames > frames_logged:
                jobs.add_frame(job_id, p.frames - 1, s.to_dict())
                frames_logged = p.frames
        jobs.update_progress(job_id, values)

    try:
        dem = dems.get(job.dem_id)
        if dem is None or dem.status != "ready" or not dem.mosaic_path:
            raise DemError(f"DEM '{job.dem_id}' is not ready.")
        req = ScenarioRequest.model_validate(job.scenario)
        logger.info("job {} started: {}", job_id, req.name)
        summary = execute_run(
            req,
            Path(dem.mosaic_path),
            run_dir,
            dem_info=dem.info,
            dem_name=dem.name,
            on_started=lambda prov, grid: jobs.set_started(job_id, prov, grid),
            on_progress=on_progress,
            should_cancel=should_cancel,
        )
        jobs.update_progress(
            job_id,
            {
                "sim_t": req.t_end,
                "frames": summary["frames"],
                "steps": summary["steps"],
                "eta_s": 0.0,
            },
        )
        jobs.finish(job_id, "completed")
        logger.info("job {} completed", job_id)
    except RunCancelled:
        jobs.finish(job_id, "cancelled")
        logger.warning("job {} cancelled", job_id)
    except Exception as exc:  # noqa: BLE001 - every failure must be recorded
        logger.error("job {} failed: {}\n{}", job_id, exc, traceback.format_exc())
        jobs.finish(job_id, "failed", f"{type(exc).__name__}: {exc}")
        sys.exit(1)
