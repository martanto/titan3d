"""Run a Titan2D-style block-and-ash / debris flow on a synthetic volcano
and export frames for the three.js viewer.

    python run_demo.py --out flow.json
"""
import argparse
import json
import time

import numpy as np

from granflow import FlowParams, Solver, State, paraboloid_pile, synthetic_volcano
from granflow.export import bundle, write


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=320)
    ap.add_argument("--dx", type=float, default=30.0)
    ap.add_argument("--t-end", type=float, default=240.0)
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--phi-bed", type=float, default=24.0)
    ap.add_argument("--phi-int", type=float, default=34.0)
    ap.add_argument("--rheology", default="coulomb")
    ap.add_argument("--pressure", default="savage-hutter")
    ap.add_argument("--pile-h", type=float, default=60.0)
    ap.add_argument("--pile-r", type=float, default=280.0)
    ap.add_argument("--out", default="flow.json")
    a = ap.parse_args()

    x, y, b = synthetic_volcano(n=a.n, dx=a.dx, base_r=3000.0)
    # pile sits in the crater, offset slightly toward the breach
    az = np.radians(200.0)
    xc, yc = 120 * np.sin(az), 120 * np.cos(az)
    h0 = paraboloid_pile(x, y, xc, yc, a.pile_h, a.pile_r)

    p = FlowParams(rheology=a.rheology, phi_bed_deg=a.phi_bed, phi_int_deg=a.phi_int,
                   earth_pressure=a.pressure)
    solver = Solver(b, a.dx, p)
    s = State(h0.copy(), np.zeros_like(h0), np.zeros_like(h0))
    vol0 = h0.sum() * a.dx ** 2

    X, Y = np.meshgrid(x, y)
    R = np.hypot(X - xc, Y - yc)
    frames, stats = [], []
    t0 = time.time()
    for st in solver.run(s, a.t_end, a.every):
        u = np.where(st.h > p.h_dry, np.hypot(st.hu, st.hv) / np.maximum(st.h, p.h_dry), 0)
        wet = st.h > 0.1
        frames.append((st.h.astype(np.float32), u.astype(np.float32)))
        stats.append({
            "t": round(st.t, 2),
            "vol": round(float(st.h.sum() * a.dx ** 2 / vol0), 5),
            "hmax": round(float(st.h.max()), 2),
            "umax": round(float(u.max()), 2),
            "area": round(float(wet.sum() * a.dx ** 2 / 1e6), 4),        # km^2
            "runout": round(float(R[wet].max() if wet.any() else 0.0), 1),  # m
            "steps": st.step,
        })
        print(f"t={st.t:6.1f}s  steps={st.step:5d}  hmax={stats[-1]['hmax']:6.1f}  "
              f"umax={stats[-1]['umax']:5.1f}  runout={stats[-1]['runout']:6.0f}  "
              f"vol={stats[-1]['vol']:.4f}  ({time.time()-t0:.1f}s)")

    meta = {"title": "Synthetic stratovolcano — summit pile collapse",
            "rheology": p.rheology, "phi_bed": p.phi_bed_deg, "phi_int": p.phi_int_deg,
            "pressure": p.earth_pressure, "volume_m3": float(vol0),
            "pile": {"x": xc, "y": yc, "h": a.pile_h, "r": a.pile_r},
            "every": a.every, "t_end": a.t_end}
    data = bundle(b, a.dx, frames, stats, meta)
    write(a.out, data)
    print("wrote", a.out, f"{sum(len(v) for v in data.values() if isinstance(v, str))/1e6:.2f} MB payload")


if __name__ == "__main__":
    main()
