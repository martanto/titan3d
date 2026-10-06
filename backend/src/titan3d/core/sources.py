"""Material sources: paraboloid piles (initial) and flux (vent) sources (time-dependent)."""

from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np

from titan3d.core.grid import Grid
from titan3d.core.params import FloatArray, FluxSource, PileSource


def paraboloid(
    x: FloatArray, y: FloatArray, xc: float, yc: float, height: float, radius: float
) -> FloatArray:
    """Paraboloid ``height · (1 - r²/R²)`` clipped at zero, on the ``(y, x)`` mesh."""
    X, Y = np.meshgrid(x, y)
    r2 = ((X - xc) ** 2 + (Y - yc) ** 2) / radius**2
    return np.clip(height * (1.0 - r2), 0.0, None)


def pile_depth(grid: Grid, piles: Sequence[PileSource]) -> FloatArray:
    """Initial depth from the sum of all piles [m]."""
    h = np.zeros(grid.b.shape, dtype=np.float64)
    for p in piles:
        h += paraboloid(grid.x, grid.y, p.x, p.y, p.height, p.radius)
    return h


@dataclass
class _Footprint:
    source: FluxSource
    window: tuple[slice, slice]
    profile: FloatArray  # paraboloid shape with peak 1
    ux: float
    uy: float


class FluxSources:
    """Applies flux sources exactly over arbitrary time steps.

    The depth added during ``[t0, t1]`` is
    ``influx · profile · |[t0, t1] ∩ [start, end]|``, so the injected volume does
    not depend on how the time steps fall.
    """

    def __init__(self, grid: Grid, sources: Sequence[FluxSource], dtype: np.dtype):
        """Pre-compute each source's footprint on the grid."""
        self.dx = grid.dx
        self.footprints: list[_Footprint] = []
        for s in sources:
            i0 = max(int(np.floor((s.x - s.radius - grid.x0) / grid.dx)), 0)
            i1 = min(int(np.ceil((s.x + s.radius - grid.x0) / grid.dx)) + 1, grid.nx)
            j0 = max(int(np.floor((s.y - s.radius - grid.y0) / grid.dx)), 0)
            j1 = min(int(np.ceil((s.y + s.radius - grid.y0) / grid.dx)) + 1, grid.ny)
            if i0 >= i1 or j0 >= j1:
                continue
            prof = paraboloid(grid.x[i0:i1], grid.y[j0:j1], s.x, s.y, 1.0, s.radius)
            az = np.radians(s.direction_deg)
            self.footprints.append(
                _Footprint(
                    source=s,
                    window=(slice(j0, j1), slice(i0, i1)),
                    profile=prof.astype(dtype),
                    ux=float(s.speed * np.sin(az)),
                    uy=float(s.speed * np.cos(az)),
                )
            )

    def __bool__(self) -> bool:
        """Whether any source touches the grid."""
        return bool(self.footprints)

    def footprint_volume(self) -> float:
        """Discrete total volume all sources will inject [m³]."""
        return sum(
            float(f.profile.sum(dtype=np.float64))
            * self.dx**2
            * f.source.influx
            * f.source.duration
            for f in self.footprints
        )

    def apply(
        self, h: FloatArray, hu: FloatArray, hv: FloatArray, t0: float, t1: float
    ) -> float:
        """Add source material for the interval ``[t0, t1]`` in place.

        Args:
            h: Full-grid depth.
            hu: Full-grid x-momentum.
            hv: Full-grid y-momentum.
            t0: Interval start [s].
            t1: Interval end [s].

        Returns:
            Volume added [m³].
        """
        added = 0.0
        for f in self.footprints:
            dt_on = min(t1, f.source.end) - max(t0, f.source.start)
            if dt_on <= 0.0:
                continue
            dh = f.profile * (f.source.influx * dt_on)
            h[f.window] += dh
            if f.ux or f.uy:
                hu[f.window] += dh * f.ux
                hv[f.window] += dh * f.uy
            added += float(dh.sum(dtype=np.float64)) * self.dx**2
        return added
