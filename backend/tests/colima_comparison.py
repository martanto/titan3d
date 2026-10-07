"""Opt-in Colima comparison helpers; outputs belong in tests/out_colima_comparison.

This harness deliberately does not change the production solver or source model.
"""

import sys
import json
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from dataclasses import asdict

import numpy as np
import rasterio
from rasterio.enums import Resampling

from titan3d.core.grid import Grid
from titan3d.core.stats import frame_stats
from titan3d.core.params import State, FlowParams
from titan3d.core.solver import Solver
from titan3d.core.numerics import velocity


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).parent / "out_colima_comparison"
CENTER = (644956.0, 2157970.0)
RADIUS = 55.0
HEIGHT = 30.0
ANALYTIC_VOLUME = np.pi * RADIUS**2 * HEIGHT


def cylinder_depth(grid: Grid) -> np.ndarray:
    """Exact disk/cell overlap by quadrature, resolving edge cells reproducibly.

    Interior/exterior cells are exact; boundary cells use 32 x 32 midpoint
    integration. This reduces grid-alignment errors without rescaling volume.
    """
    xx, yy = np.meshgrid(grid.x - CENTER[0], grid.y - CENTER[1])
    radius = np.hypot(xx, yy)
    margin = grid.dx / np.sqrt(2)
    h = np.where(radius < RADIUS - margin, HEIGHT, 0.0)
    for j, i in zip(*np.nonzero(np.abs(radius - RADIUS) <= margin), strict=True):
        offsets = ((np.arange(32) + 0.5) / 32 - 0.5) * grid.dx
        r2 = (xx[j, i] + offsets[None, :]) ** 2 + (yy[j, i] + offsets[:, None]) ** 2
        h[j, i] = HEIGHT * np.mean(r2 < RADIUS**2)
    return h


def rasterize_cells(bounds: np.ndarray, depth: np.ndarray, grid: Grid) -> np.ndarray:
    """Conservative rectangle/cell overlap, north-up array convention.

    Input cells must be non-overlapping axis-aligned leaf cells. No nearest-cell
    interpolation or centre-point sampling is used. Bounds are west,south,east,north.
    """
    result = np.zeros_like(grid.b, dtype=np.float64)
    west, south, _, _ = grid.bounds
    wet = depth != 0
    if not wet.any():
        return result
    x0, y0, x1, y1 = bounds[wet].T
    h = depth[wet]
    ia = np.maximum(0, np.floor((x0 - west) / grid.dx).astype(int))
    ib = np.minimum(grid.nx, np.ceil((x1 - west) / grid.dx).astype(int))
    ja = np.maximum(0, np.floor((y0 - south) / grid.dx).astype(int))
    jb = np.minimum(grid.ny, np.ceil((y1 - south) / grid.dx).astype(int))
    # Group by raster span so a few coarse, almost-dry cells do not make every
    # fine cell iterate over hundreds of unrelated raster pixels.
    spans = np.column_stack((ib - ia, jb - ja))
    for ni, nj in np.unique(spans, axis=0):
        selected = np.all(spans == (ni, nj), axis=1)
        gx0, gy0, gx1, gy1 = x0[selected], y0[selected], x1[selected], y1[selected]
        gh, gia, gja = h[selected], ia[selected], ja[selected]
        for dj in range(max(0, int(nj))):
            j = gja + dj
            y = south + j * grid.dx
            wy = np.maximum(0, np.minimum(y + grid.dx, gy1) - np.maximum(y, gy0))
            for di in range(max(0, int(ni))):
                i = gia + di
                x = west + i * grid.dx
                wx = np.maximum(
                    0,
                    np.minimum(x + grid.dx, gx1) - np.maximum(x, gx0),
                )
                np.add.at(result, (j, i), gh * wx * wy / grid.dx**2)
    return result


def depth_metrics(reference: np.ndarray, candidate: np.ndarray, dx: float) -> dict:
    """Depth errors over the wet union and footprint intersection/union."""
    if reference.shape != candidate.shape:
        raise ValueError("Comparison rasters must share a shape")
    if dx <= 0 or any(
        not np.isfinite(a).all() or np.any(a < 0) for a in (reference, candidate)
    ):
        raise ValueError(
            "Depths must be finite and nonnegative; spacing must be positive"
        )
    a, b = reference > 0.1, candidate > 0.1
    union = a | b
    diff = candidate[union] - reference[union]
    return {
        "threshold_m": 0.1,
        "wet_union_cells": int(union.sum()),
        "footprint_iou": float((a & b).sum() / union.sum()) if union.any() else 1.0,
        "mae_m": float(np.abs(diff).mean()) if diff.size else 0.0,
        "rmse_m": float(np.sqrt(np.mean(diff**2))) if diff.size else 0.0,
        "bias_m": float(diff.mean()) if diff.size else 0.0,
        "reference_area_m2": float(a.sum() * dx**2),
        "candidate_area_m2": float(b.sum() * dx**2),
    }


def read_adaptive_state(element, directory: Path):
    """Read Titan2D XDMF fields and projected, rectangular leaf-cell areas."""
    import h5py

    def read(item):
        filename, dataset = item.text.strip().split(":", 1)
        with h5py.File(directory / filename, "r") as hdf:
            return np.asarray(hdf[dataset])

    points = read(element.find("Geometry/DataItem"))
    connections = read(element.find("Topology/DataItem")).astype(int)
    vertices = points[connections, :2]
    lo, hi = vertices.min(axis=1), vertices.max(axis=1)
    bounds = np.column_stack((lo, hi))
    area = np.prod(hi - lo, axis=1)
    rectangular = np.all(
        np.isclose(vertices, lo[:, None, :], rtol=0, atol=1e-7)
        | np.isclose(vertices, hi[:, None, :], rtol=0, atol=1e-7)
    )
    if np.any(area <= 0) or not rectangular:
        raise ValueError("Expected positive axis-aligned adaptive cell areas")
    fields = {
        attr.attrib["Name"]: read(attr.find("DataItem")).reshape(-1)
        for attr in element.findall("Attribute")
    }
    h = fields["Pile Height"]
    if not np.isfinite(h).all() or np.min(h) < 0:
        raise ValueError("Invalid adaptive depth")
    if any(
        len(fields[name]) != len(area)
        for name in ("Pile Height", "X_Momentum", "Y_Momentum")
    ):
        raise ValueError("Adaptive field lengths do not match topology")
    return bounds, area, h, fields["X_Momentum"], fields["Y_Momentum"]


def load_grid(dx: float) -> Grid:
    """Resample identical full DEM bounds; dx must divide the native extent."""
    with rasterio.open(ROOT / "dem/colimafinemini.tif") as src:
        width, height = (
            src.bounds.right - src.bounds.left,
            src.bounds.top - src.bounds.bottom,
        )
        nx, ny = round(width / dx), round(height / dx)
        if not np.isclose(nx * dx, width) or not np.isclose(ny * dx, height):
            raise ValueError("Grid spacing must divide the DEM extent")
        b = src.read(1, out_shape=(ny, nx), resampling=Resampling.bilinear)
        if not np.isfinite(b).all() or (
            src.nodata is not None and np.any(b == src.nodata)
        ):
            raise ValueError("Comparison DEM must have complete finite coverage")
        return Grid(
            np.flipud(b).astype(np.float64).copy(),
            dx,
            src.bounds.left + dx / 2,
            src.bounds.bottom + dx / 2,
            str(src.crs),
        )


def run_titan3d(dx: float, duration: float, interval: float) -> None:
    """Run a cylinder directly through the unchanged production Solver."""
    import numba

    numba.set_num_threads(min(8, numba.get_num_threads()))
    out = OUTPUT / f"titan3d-{dx:g}m"
    out.mkdir(parents=True, exist_ok=True)
    grid = load_grid(dx)
    h = cylinder_depth(grid)
    state = State(h, np.zeros_like(h), np.zeros_like(h))
    p = FlowParams(phi_bed_deg=27, phi_int_deg=37)
    solver = Solver(grid, p)
    volume = float(h.sum()) * dx**2
    stats = []
    saved_max = np.zeros_like(h)
    start = time.perf_counter()
    for k, s in enumerate(solver.run(state, duration, interval)):
        speed = velocity(s.h, np.hypot(s.hu, s.hv), p.h_dry)
        np.maximum(saved_max, s.h, out=saved_max)
        np.savez_compressed(
            out / f"frame-{k:04d}.npz",
            h=s.h.astype("float32"),
            speed=speed.astype("float32"),
            t=s.t,
        )
        stats.append(
            asdict(frame_stats(s, dx, grid.x, grid.y, CENTER, volume, p.h_dry))
        )
        if k % 10 == 0:
            print(f"titan3d {dx:g} m: t={s.t:g} s, steps={s.step}", flush=True)
    np.savez_compressed(
        out / "maxima.npz",
        saved_h_max=saved_max,
        every_step_h_max=solver.h_max,
        b=grid.b,
    )
    manifest = {
        "model": "titan3d",
        "dx_m": dx,
        "duration_s": duration,
        "interval_s": interval,
        "initial_volume_m3": volume,
        "analytic_volume_m3": ANALYTIC_VOLUME,
        "params": asdict(p),
        "wall_time_s": time.perf_counter() - start,
        "dem_sha256": hashlib.sha256(
            (ROOT / "dem/colimafinemini.tif").read_bytes()
        ).hexdigest(),
        "grid_bounds": grid.bounds,
        "crs": grid.crs,
        "python": sys.version,
        "numpy": np.__version__,
        "numba": numba.__version__,
        "rasterio": rasterio.__version__,
        "numba_threads": numba.get_num_threads(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "stats.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dx", type=float, default=5)
    parser.add_argument("--duration", type=float, default=150)
    parser.add_argument("--interval", type=float, default=1)
    args = parser.parse_args()
    run_titan3d(args.dx, args.duration, args.interval)
