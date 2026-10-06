"""Pack a simulation into a compact JSON bundle for the three.js viewer.

Fields are quantised to bytes and zlib-compressed, then base64 encoded:
  terrain  uint16  (b - zmin) / (zmax - zmin)
  depth    uint8   sqrt(h / h_max)        (sqrt keeps thin margins visible)
  speed    uint8   |u| / u_max
"""
from __future__ import annotations

import base64
import json
import zlib

import numpy as np


def _pack(arr: np.ndarray) -> str:
    return base64.b64encode(zlib.compress(np.ascontiguousarray(arr).tobytes(), 9)).decode()


def bundle(b, dx, frames, stats, meta, step=1):
    b = b[::step, ::step]
    hs = np.stack([f[0][::step, ::step] for f in frames])
    vs = np.stack([f[1][::step, ::step] for f in frames])
    h_max_field = hs.max(axis=0)
    zmin, zmax = float(b.min()), float(b.max())
    hmax = float(max(hs.max(), 1e-3))
    vmax = float(max(vs.max(), 1e-3))
    terr = np.round((b - zmin) / (zmax - zmin) * 65535).astype("<u2")
    q = lambda a, m, f: np.round(np.clip(f(a / m), 0, 1) * 255).astype(np.uint8)
    depth = q(hs, hmax, np.sqrt)
    speed = q(vs, vmax, lambda a: a)
    return {
        "meta": {**meta, "dx": dx * step, "ny": b.shape[0], "nx": b.shape[1],
                 "nframes": len(frames), "zmin": zmin, "zmax": zmax,
                 "hmax": hmax, "vmax": vmax},
        "stats": stats,
        "terrain": _pack(terr),
        "depth": _pack(depth),
        "speed": _pack(speed),
        "hmaxField": _pack(q(h_max_field, hmax, np.sqrt)),
    }


def write(path, data):
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
