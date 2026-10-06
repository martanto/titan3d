"""Per-frame summary statistics."""

from dataclasses import asdict, dataclass

import numpy as np

from titan3d.core.params import State, FloatArray
from titan3d.core.numerics import velocity


WET_THRESHOLD = 0.1
"""Depth above which a cell counts as inundated [m]."""


@dataclass(frozen=True)
class FrameStats:
    """Summary of one output frame.

    Attributes:
        t: Simulation time [s].
        steps: Completed time steps.
        vol: Volume in the domain as a fraction of the released volume.
        vol_out: Volume that left the domain, fraction of released.
        released_m3: Released volume so far (piles + sources) [m³].
        hmax: Maximum depth [m].
        umax: Maximum speed [m/s].
        area: Inundated area (h > 0.1 m) [km²].
        runout: Farthest inundated distance from the reference point [m].
    """

    t: float
    steps: int
    vol: float
    vol_out: float
    released_m3: float
    hmax: float
    umax: float
    area: float
    runout: float

    def to_dict(self) -> dict[str, float | int]:
        """Rounded dict for JSON output."""
        d = asdict(self)
        rounding = {"t": 2, "vol": 6, "vol_out": 6, "released_m3": 0, "hmax": 2}
        rounding |= {"umax": 2, "area": 4, "runout": 1}
        return {
            k: (round(v, rounding[k]) if k in rounding else v) for k, v in d.items()
        }


def frame_stats(
    s: State,
    dx: float,
    x: FloatArray,
    y: FloatArray,
    ref_xy: tuple[float, float],
    initial_volume: float,
    h_dry: float,
) -> FrameStats:
    """Compute summary statistics for a state.

    Args:
        s: Solver state.
        dx: Cell size [m].
        x: Cell-centre eastings [m].
        y: Cell-centre northings [m].
        ref_xy: Reference point for runout (first source centre) [m].
        initial_volume: Volume of the initial piles [m³].
        h_dry: Dry threshold [m].
    """
    released = initial_volume + s.vol_source
    vol = float(s.h.sum(dtype=np.float64)) * dx**2
    wet = s.h > WET_THRESHOLD
    hmax = float(np.max(s.h)) if s.h.size else 0.0
    umax = 0.0
    runout = 0.0
    if wet.any():
        jj, ii = np.nonzero(wet)
        speed = velocity(s.h[wet], np.hypot(s.hu[wet], s.hv[wet]), h_dry)
        umax = float(np.max(speed))
        r = np.hypot(x[ii] - ref_xy[0], y[jj] - ref_xy[1])
        runout = float(np.max(r))
    return FrameStats(
        t=float(s.t),
        steps=int(s.step),
        vol=vol / released if released > 0 else 0.0,
        vol_out=s.vol_out / released if released > 0 else 0.0,
        released_m3=released,
        hmax=hmax,
        umax=umax,
        area=float(wet.sum()) * dx**2 / 1e6,
        runout=runout,
    )
