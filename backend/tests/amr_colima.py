"""Fresh Colima AMR/uniform runs, with native-leaf and output-raster statistics.

Run from backend/: uv run --no-sync python tests/amr_colima.py --model amr
Raw outputs remain in tests/out_amr/; plotting is a separate command.
"""

import json
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from dataclasses import asdict

import numba
import numpy as np
import psutil
from colima_comparison import ROOT, CENTER, load_grid, cylinder_depth

from titan3d.core.amr import AdaptiveSolver
from titan3d.core.grid import Grid
from titan3d.core.stats import frame_stats
from titan3d.core.params import FlowParams
from titan3d.core.solver import Solver
from titan3d.core.numerics import velocity


OUTPUT = Path(__file__).parent / "out_amr"


def run(model: str, dx: float, duration: float, interval: float) -> None:
    """Use matched terrain, release and physics; do not fit parameters."""
    numba.set_num_threads(min(8, numba.get_num_threads()))
    out = OUTPUT / f"{model}-{dx:g}m"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists():
        raise FileExistsError(
            f"Completed run already exists: {out}; move it before replaying"
        )
    p = FlowParams(phi_bed_deg=27, phi_int_deg=37, amr=model == "amr")
    cls = AdaptiveSolver if p.amr else Solver
    # Compile kernels on a separate tiny grid before measuring the case.
    warmup_start = time.perf_counter()
    warm = cls(Grid(np.zeros((16, 16)), dx), p)
    warm_state = warm.initial_state(np.ones((16, 16)))
    warm.step(warm_state, 0.001)
    warmup = time.perf_counter() - warmup_start
    g = load_grid(dx)
    h0 = cylinder_depth(g)
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    start = time.perf_counter()
    solver = cls(g, p)
    state = solver.initial_state(h0)
    v0 = solver.volume(state.h)
    envelope = np.zeros_like(h0)
    stats = []
    max_mass_error = 0.0

    def on_step(s):
        nonlocal peak_rss, max_mass_error
        peak_rss = max(peak_rss, process.memory_info().rss)
        error = abs(solver.volume(s.h) + s.vol_out - v0 - s.vol_source) / v0
        max_mass_error = max(max_mass_error, error)

    for index, s in enumerate(solver.run(state, duration, interval, on_step)):
        speed = velocity(s.h, np.hypot(s.hu, s.hv), p.h_dry)
        np.maximum(envelope, s.h, out=envelope)
        np.savez_compressed(out / f"frame-{index:04d}.npz", h=s.h, speed=speed, t=s.t)
        row = asdict(frame_stats(s, dx, g.x, g.y, CENTER, v0, p.h_dry))
        if isinstance(solver, AdaptiveSolver):
            mesh = solver.mesh
            h, qx, qy = (mesh.restrict(a) for a in (s.h, s.hu, s.hv))
            wet = h > 0.1
            native_speed = np.divide(
                np.hypot(qx, qy), h, out=np.zeros_like(h), where=wet
            )
            native_runout = (
                float(np.hypot(mesh.x[wet] - CENTER[0], mesh.y[wet] - CENTER[1]).max())
                if wet.any()
                else 0
            )
            row.update(
                leaf_cells=mesh.n,
                refined_parents=int(mesh.refined.sum()),
                regrids=solver.regrids,
                native_runout=native_runout,
                native_umax=float(native_speed.max()),
                native_area_km2=float(mesh.area[wet].sum() / 1e6),
            )
        stats.append(row)
        if index % 10 == 0:
            print(
                f"{model} {dx:g} m: t={s.t:g}, steps={s.step}, leaves={row.get('leaf_cells', g.b.size)}, elapsed={time.perf_counter() - start:.1f}s",
                flush=True,
            )
    np.savez_compressed(
        out / "maxima.npz", saved_h_max=envelope, every_step_h_max=solver.h_max, b=g.b
    )
    manifest = {
        "model": model,
        "dx_m": dx,
        "duration_s": duration,
        "interval_s": interval,
        "initial_volume_m3": v0,
        "params": asdict(p),
        "wall_time_s": time.perf_counter() - start,
        "warmup_s": warmup,
        "process_peak_rss_mb": peak_rss / 1e6,
        "max_mass_budget_relative_error": max_mass_error,
        "grid_bounds": g.bounds,
        "grid_shape": g.b.shape,
        "crs": g.crs,
        "dem_sha256": hashlib.sha256(
            (ROOT / "dem/colimafinemini.tif").read_bytes()
        ).hexdigest(),
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__),
                ROOT / "backend/src/titan3d/core/amr.py",
                ROOT / "backend/src/titan3d/core/amr_mesh.py",
                ROOT / "backend/src/titan3d/core/numerics.py",
            )
        },
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff"], cwd=ROOT)
        ).hexdigest(),
        "numpy": np.__version__,
        "numba": numba.__version__,
        "numba_threads": numba.get_num_threads(),
        "raster_definition": "conservative finest-grid prolongation; maxima at shared saved times",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("amr", "uniform"), default="amr")
    parser.add_argument("--dx", type=float, default=5)
    parser.add_argument("--duration", type=float, default=150)
    parser.add_argument("--interval", type=float, default=1)
    args = parser.parse_args()
    run(args.model, args.dx, args.duration, args.interval)
