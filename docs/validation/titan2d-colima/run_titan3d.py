"""Run titan3d on Titan2D's colimafinemini example with matched inputs.

Usage: uv run python run_titan3d.py OUT_DIR [--dx 5] [--t-end 150] [--every 5]
"""
import os, sys, json, time, argparse
from pathlib import Path
import numpy as np
import rasterio
from titan3d.core.grid import Grid
from titan3d.core.params import FlowParams, Rheology, EarthPressure, Backend
from titan3d.core.solver import Solver
from titan3d.core.numerics import velocity

DEM = os.environ.get("COLIMA_DEM", "colimafinemini.geotiff")  # titan2d/share/titan2d_examples/dem/
XC, YC, H, R = 644956.0, 2157970.0, 30.0, 55.0   # Titan2D addPile (Cylinder)

ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("--dx", type=float, default=5.0)
ap.add_argument("--t-end", type=float, default=150.0); ap.add_argument("--every", type=float, default=5.0)
ap.add_argument("--phi-bed", type=float, default=27.0); ap.add_argument("--phi-int", type=float, default=37.0)
ap.add_argument("--pressure", default="savage-hutter"); ap.add_argument("--no-curvature", action="store_true")
a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

with rasterio.open(DEM) as src:
    b = src.read(1).astype(np.float64)
    step = int(round(a.dx / src.res[0]))
    b = b[::step, ::step] if step > 1 else b
    dx = src.res[0] * step
    left, top = src.bounds.left, src.bounds.top
ny, nx = b.shape
b = np.ascontiguousarray(b[::-1])                         # j increases north
grid = Grid(b=b, dx=dx, x0=left + dx / 2, y0=top - ny * dx + dx / 2, crs="EPSG:32613")
X, Y = np.meshgrid(grid.x, grid.y)
h0 = np.where((X - XC) ** 2 + (Y - YC) ** 2 <= R ** 2, H, 0.0)

p = FlowParams(rheology=Rheology.COULOMB, phi_bed_deg=a.phi_bed, phi_int_deg=a.phi_int,
               earth_pressure=EarthPressure(a.pressure), curvature=not a.no_curvature,
               backend=Backend.NUMBA)
solver = Solver(grid, p)
v0 = solver.volume(h0)
print(f"grid {ny}x{nx} @ {dx} m, pile cells {(h0>0).sum()}, V0 {v0:.0f} m3 (analytic {np.pi*R*R*H:.0f})", flush=True)
s = solver.initial_state(h0)
ts, t0 = [], time.perf_counter()
frames = []
for st in solver.run(s, a.t_end, a.every):
    sp = velocity(st.h, np.hypot(st.hu, st.hv), p.h_dry)
    wet = st.h > 0.1
    r = np.hypot(X - XC, Y - YC)
    ts.append(dict(t=st.t, steps=st.step, vol=solver.volume(st.h), vol_out=st.vol_out,
                   hmax=float(st.h.max()), umax=float(sp.max()),
                   area_km2=float(wet.sum() * dx * dx / 1e6),
                   runout_m=float(r[wet].max()) if wet.any() else 0.0,
                   wall_s=time.perf_counter() - t0))
    frames.append(st.h.astype(np.float32))
    e = ts[-1]
    print(f"t={e['t']:6.1f} steps={e['steps']:6d} V={e['vol']:.0f} hmax={e['hmax']:.2f} umax={e['umax']:.1f} runout={e['runout_m']:.0f} wall={e['wall_s']:.0f}s", flush=True)
np.savez_compressed(out / "result.npz", b=b, x=grid.x, y=grid.y, h_max=solver.h_max, u_max=solver.u_max,
                    h_final=frames[-1], frames=np.stack(frames), h0=h0)
json.dump(dict(dx=dx, v0=v0, params=vars(a), ts=ts, backend=str(solver.backend)), open(out / "summary.json", "w"), indent=1)
