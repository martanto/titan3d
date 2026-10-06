"""Depth-averaged granular-flow solver in the spirit of Titan2D.

Governing equations (plan-view Cartesian coordinates on a bed ``b(x, y)``)::

    h_t   + (hu)_x + (hv)_y                      = S_h
    (hu)_t + (hu² + ½ k g h²)_x + (huv)_y        = −g h b_x − F_x
    (hv)_t + (huv)_x + (hv² + ½ k g h²)_y        = −g h b_y − F_y

with basal resistance ``F`` opposing the velocity (see :mod:`.rheology`), an
optional bed-curvature term in the normal stress (:mod:`.curvature`), and flux
sources ``S_h`` (:mod:`.sources`).

Time integration is SSP-RK2 (Heun) with an adaptive CFL step. Friction is an
implicit stopping step after each stage. Every stage is computed only on the
*active window* — the bounding box of cells with ``h > 0`` plus a margin —
which is exact because dry cells with zero momentum produce zero flux. The box
is tracked incrementally, so a step never scans the whole grid.
"""

import warnings
from typing import Protocol
from collections.abc import Callable, Iterator, Sequence

import numpy as np

from titan3d.core.grid import Grid
from titan3d.core.params import (
    G,
    State,
    Backend,
    Rheology,
    FloatArray,
    FlowParams,
    FluxSource,
    EarthPressure,
)
from titan3d.core.sources import FluxSources
from titan3d.core.numerics import GHOST, velocity, rhs_block
from titan3d.core.rheology import (
    apply_friction,
    max_earth_pressure,
    earth_pressure_block,
    earth_pressure_coefficients,
)
from titan3d.core.curvature import BedGeometry, bed_geometry


Window = tuple[slice, slice]
Box = tuple[int, int, int, int]

MARGIN = 4
"""Dry cells kept around the wet box; covers two RK stages of spreading (one
cell each) plus the two-cell MUSCL stencil."""


class Kernels(Protocol):
    """Backend-specific implementations of the per-cell work."""

    backend: Backend

    def rhs(
        self,
        H: FloatArray,
        B: FloatArray,
        HU: FloatArray,
        HV: FloatArray,
        K: FloatArray,
        dx: float,
        h_dry: float,
    ) -> tuple[FloatArray, FloatArray, FloatArray, list[FloatArray]]:
        """Flux divergence on a padded block."""
        ...

    def earth_pressure(
        self, H: FloatArray, HU: FloatArray, HV: FloatArray, dx: float
    ) -> FloatArray:
        """Earth-pressure coefficient on a padded block."""
        ...

    def friction(
        self, h: FloatArray, hu: FloatArray, hv: FloatArray, dt: float, win: Window
    ) -> tuple[FloatArray, FloatArray]:
        """Implicit friction on a window."""
        ...

    def max_speed(self, h: FloatArray, hu: FloatArray, hv: FloatArray) -> float:
        """Largest characteristic speed on a window."""
        ...

    def update_max(
        self,
        h: FloatArray,
        hu: FloatArray,
        hv: FloatArray,
        h_max: FloatArray,
        u_max: FloatArray,
    ) -> None:
        """Update running maxima in place on a window."""
        ...

    def wet_box(self, h: FloatArray, j0: int, i0: int) -> Box | None:
        """Absolute bounding box of ``h > 0`` inside a window."""
        ...


class NumpyKernels:
    """Reference implementation in vectorised NumPy."""

    backend = Backend.NUMPY

    def __init__(self, p: FlowParams, geom: BedGeometry, k_max: float, tan_bed: float):
        self.p, self.geom, self.k_max, self.tan_bed = p, geom, k_max, tan_bed

    def rhs(self, H, B, HU, HV, K, dx, h_dry):  # noqa: ANN001, ANN201, D102
        return rhs_block(H, B, HU, HV, K, dx, h_dry)

    def earth_pressure(self, H, HU, HV, dx):  # noqa: ANN001, ANN201, D102
        return earth_pressure_block(H, HU, HV, dx, self.p)

    def friction(self, h, hu, hv, dt, win):  # noqa: ANN001, ANN201, D102
        return apply_friction(h, hu, hv, dt, self.geom, win, self.p, self.tan_bed)

    def max_speed(self, h, hu, hv):  # noqa: ANN001, ANN201, D102
        u = velocity(h, hu, self.p.h_dry)
        v = velocity(h, hv, self.p.h_dry)
        c = np.sqrt(self.k_max * G * h)
        return max(float(np.max(np.abs(u) + c)), float(np.max(np.abs(v) + c)))

    def update_max(self, h, hu, hv, h_max, u_max):  # noqa: ANN001, ANN201, D102
        np.maximum(h_max, h, out=h_max)
        speed = velocity(h, np.hypot(hu, hv), self.p.h_dry)
        np.maximum(u_max, speed, out=u_max)

    def wet_box(self, h, j0, i0):  # noqa: ANN001, ANN201, D102
        rows = np.flatnonzero(h.any(axis=1))
        if rows.size == 0:
            return None
        cols = np.flatnonzero(h.any(axis=0))
        return (
            j0 + int(rows[0]),
            j0 + int(rows[-1]) + 1,
            i0 + int(cols[0]),
            i0 + int(cols[-1]) + 1,
        )


class NumbaKernels(NumpyKernels):
    """Compiled kernels; same results as :class:`NumpyKernels` to round-off."""

    backend = Backend.NUMBA

    def __init__(self, p: FlowParams, geom: BedGeometry, k_max: float, tan_bed: float):
        from titan3d.core import kernels_numba as kn

        super().__init__(p, geom, k_max, tan_bed)
        self.kn = kn
        self.k_act, self.k_pas = earth_pressure_coefficients(
            p.phi_int_deg, p.phi_bed_deg
        )

    def rhs(self, H, B, HU, HV, K, dx, h_dry):  # noqa: ANN001, ANN201, D102
        return self.kn.rhs_block_numba(H, B, HU, HV, K, dx, h_dry)

    def earth_pressure(self, H, HU, HV, dx):  # noqa: ANN001, ANN201, D102
        hydro = self.p.earth_pressure == EarthPressure.HYDROSTATIC
        return self.kn.earth_pressure_numba(
            H, HU, HV, dx, hydro, self.k_act, self.k_pas, self.p.h_dry
        )

    def friction(self, h, hu, hv, dt, win):  # noqa: ANN001, ANN201, D102
        g, p = self.geom, self.p
        return self.kn.friction_numba(
            h,
            hu,
            hv,
            dt,
            g.cos_theta[win],
            g.bxx[win],
            g.bxy[win],
            g.byy[win],
            g.curvature,
            p.rheology == Rheology.VOELLMY,
            self.tan_bed,
            p.mu,
            p.xi,
            p.h_dry,
        )

    def max_speed(self, h, hu, hv):  # noqa: ANN001, ANN201, D102
        return float(self.kn.max_speed_numba(h, hu, hv, self.k_max, self.p.h_dry))

    def update_max(self, h, hu, hv, h_max, u_max):  # noqa: ANN001, ANN201, D102
        self.kn.update_max_numba(h, hu, hv, h_max, u_max, self.p.h_dry)

    def wet_box(self, h, j0, i0):  # noqa: ANN001, ANN201, D102
        box = self.kn.wet_box_numba(h, j0, i0)
        return None if box[0] < 0 else tuple(int(v) for v in box)


def make_kernels(
    p: FlowParams, geom: BedGeometry, k_max: float, tan_bed: float
) -> Kernels:
    """Kernels for the requested backend, falling back to NumPy if Numba fails."""
    if p.backend == Backend.NUMBA:
        try:
            return NumbaKernels(p, geom, k_max, tan_bed)
        except ImportError as exc:  # pragma: no cover - depends on environment
            warnings.warn(f"Numba unavailable ({exc}); using NumPy", stacklevel=2)
    return NumpyKernels(p, geom, k_max, tan_bed)


def _union(a: Box | None, b: Box | None) -> Box | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3])


class Solver:
    """Granular flow on a regular grid.

    States are updated **in place** by :meth:`step`; :meth:`run` yields copies.

    Args:
        grid: Bed elevation and spacing.
        params: Material and numerical parameters.
        flux_sources: Optional vent sources.
        track_max: Track per-cell maximum depth and speed over every step.
    """

    def __init__(
        self,
        grid: Grid,
        params: FlowParams | None = None,
        flux_sources: Sequence[FluxSource] = (),
        track_max: bool = True,
    ):
        self.p = params or FlowParams()
        self.dtype = self.p.precision.dtype
        self.grid = grid
        self.dx = float(grid.dx)
        self.b = np.ascontiguousarray(grid.b, dtype=self.dtype)
        self.ny, self.nx = self.b.shape
        self.geom = bed_geometry(self.b, self.dx, self.p.curvature)
        self.tan_bed = float(np.tan(np.radians(self.p.phi_bed_deg)))
        self.k_max = max_earth_pressure(self.p)
        self.sources = FluxSources(grid, flux_sources, self.dtype)
        self.kernels = make_kernels(self.p, self.geom, self.k_max, self.tan_bed)
        self.backend = self.kernels.backend
        self.track_max = track_max
        self.h_max = np.zeros_like(self.b)
        self.u_max = np.zeros_like(self.b)

    # ----------------------------------------------------------------- state
    def initial_state(self, h0: FloatArray) -> State:
        """State at rest with depth ``h0`` (copied)."""
        h = np.array(h0, dtype=self.dtype, copy=True, order="C")
        s = State(h, np.zeros_like(h), np.zeros_like(h))
        s.box = self.kernels.wet_box(h, 0, 0)
        if self.track_max:
            np.maximum(self.h_max, h, out=self.h_max)
        return s

    def volume(self, h: FloatArray) -> float:
        """Volume of a depth field [m³]."""
        return float(h.sum(dtype=np.float64)) * self.dx**2

    # ---------------------------------------------------------------- window
    def _box(self, s: State) -> Box | None:
        if s.box is None:
            s.box = self.kernels.wet_box(s.h, 0, 0)
        return s.box

    def expand(self, box: Box, margin: int) -> Window:
        """Window around a box, clipped to the grid."""
        return (
            slice(max(box[0] - margin, 0), min(box[1] + margin, self.ny)),
            slice(max(box[2] - margin, 0), min(box[3] + margin, self.nx)),
        )

    def step_window(self, s: State) -> Window | None:
        """Window the next step is computed on, or ``None`` if all dry."""
        box = self._box(s)
        return None if box is None else self.expand(box, MARGIN)

    def _padded(self, a: FloatArray, win: Window) -> FloatArray:
        """Window of ``a`` with ``GHOST`` cells each side.

        Real neighbours are used where they exist; edge values are replicated
        only at the domain boundary (transmissive boundary).
        """
        js, is_ = win
        g = GHOST
        ja, jb = max(js.start - g, 0), min(js.stop + g, self.ny)
        ia, ib = max(is_.start - g, 0), min(is_.stop + g, self.nx)
        block = a[ja:jb, ia:ib]
        pad = (
            (g - (js.start - ja), g - (jb - js.stop)),
            (g - (is_.start - ia), g - (ib - is_.stop)),
        )
        if any(p for pair in pad for p in pair):
            block = np.pad(block, pad, mode="edge")
        return block

    # ------------------------------------------------------------------- rhs
    def _rhs(
        self, h: FloatArray, hu: FloatArray, hv: FloatArray, win: Window
    ) -> tuple[FloatArray, FloatArray, FloatArray, float]:
        """Flux divergence on the window and the net outflow rate [m³/s]."""
        H = self._padded(h, win)
        HU = self._padded(hu, win)
        HV = self._padded(hv, win)
        B = self._padded(self.b, win)
        K = self.kernels.earth_pressure(H, HU, HV, self.dx)
        dh, dhu, dhv, (fw, fe, fs, fn) = self.kernels.rhs(
            H, B, HU, HV, K, self.dx, self.p.h_dry
        )
        js, is_ = win
        out = 0.0
        if is_.start == 0:
            out -= float(fw.sum(dtype=np.float64))
        if is_.stop == self.nx:
            out += float(fe.sum(dtype=np.float64))
        if js.start == 0:
            out -= float(fs.sum(dtype=np.float64))
        if js.stop == self.ny:
            out += float(fn.sum(dtype=np.float64))
        return dh, dhu, dhv, out * self.dx

    # ------------------------------------------------------------------ step
    def max_dt(self, s: State) -> float:
        """Largest stable time step for the current state [s] (``inf`` if dry)."""
        box = self._box(s)
        if box is None:
            return np.inf
        win = self.expand(box, 0)
        smax = max(self.kernels.max_speed(s.h[win], s.hu[win], s.hv[win]), 1e-6)
        return self.p.cfl * self.dx / smax

    def step(self, s: State, dt: float) -> State:
        """Advance one SSP-RK2 step of size ``dt`` (plus sources), in place."""
        h, hu, hv = s.h, s.hu, s.hv
        win = self.step_window(s)
        box: Box | None = None
        if win is not None:
            kern = self.kernels
            h0, hu0, hv0 = h[win].copy(), hu[win].copy(), hv[win].copy()
            k1 = self._rhs(h, hu, hv, win)
            h1 = np.maximum(h0 + dt * k1[0], 0.0)
            hu1, hv1 = kern.friction(h1, hu0 + dt * k1[1], hv0 + dt * k1[2], dt, win)
            h[win], hu[win], hv[win] = h1, hu1, hv1
            k2 = self._rhs(h, hu, hv, win)
            h2 = np.maximum(0.5 * (h0 + h1 + dt * k2[0]), 0.0)
            hu2 = 0.5 * (hu0 + hu1 + dt * k2[1])
            hv2 = 0.5 * (hv0 + hv1 + dt * k2[2])
            hu2, hv2 = kern.friction(h2, hu2, hv2, 0.5 * dt, win)
            h[win], hu[win], hv[win] = h2, hu2, hv2
            s.vol_out += 0.5 * dt * (k1[3] + k2[3])
            box = kern.wet_box(h2, win[0].start, win[1].start)
        if self.sources:
            added, src_box = self._apply_sources(s, dt)
            s.vol_source += added
            box = _union(box, src_box)
        s.box = box
        s.t += dt
        s.step += 1
        if self.track_max and box is not None:
            w = self.expand(box, 0)
            self.kernels.update_max(h[w], hu[w], hv[w], self.h_max[w], self.u_max[w])
        return s

    def _apply_sources(self, s: State, dt: float) -> tuple[float, Box | None]:
        added = self.sources.apply(s.h, s.hu, s.hv, s.t, s.t + dt)
        box: Box | None = None
        for f in self.sources.footprints:
            if min(s.t + dt, f.source.end) > max(s.t, f.source.start):
                js, is_ = f.window
                box = _union(box, (js.start, js.stop, is_.start, is_.stop))
        return added, box

    # ------------------------------------------------------------------- run
    def next_event(self, t: float) -> float:
        """Next source start time after ``t``; steps never straddle it."""
        times = [f.source.start for f in self.sources.footprints if f.source.start > t]
        return min(times, default=np.inf)

    def source_dt(self, s: State) -> float:
        """Time-step limit while sources are injecting [s].

        The wave speed is estimated from the depth the source would reach after
        one more second of extrusion, so material added in a step cannot
        violate the CFL condition. Capped at 1 s.
        """
        dt = np.inf
        for f in self.sources.footprints:
            src = f.source
            if not (src.start <= s.t < src.end):
                continue
            h_ref = float(np.max(s.h[f.window])) + src.influx * 1.0
            c = src.speed + np.sqrt(self.k_max * G * max(h_ref, self.p.h_dry))
            dt = min(dt, self.p.cfl * self.dx / c, 1.0)
        return dt

    def run(
        self,
        s: State,
        t_end: float,
        output_every: float,
        on_step: Callable[[State], None] | None = None,
    ) -> Iterator[State]:
        """Advance to ``t_end``, yielding copies every ``output_every`` seconds.

        Args:
            s: Initial state (yielded first; advanced in place afterwards).
            t_end: End time [s].
            output_every: Output interval [s].
            on_step: Called after every step; may raise to abort the run.

        Yields:
            Copies of the state at ``t = s.t, s.t + output_every, …, t_end``.
        """
        yield s.copy()
        next_out = s.t + output_every
        while s.t < t_end - 1e-9:
            # all-dry with no active source: dt jumps to the next event/output
            dt = min(
                self.max_dt(s),
                self.source_dt(s),
                self.next_event(s.t) - s.t,
                next_out - s.t,
                t_end - s.t,
            )
            s = self.step(s, dt)
            if on_step is not None:
                on_step(s)
            if s.t >= next_out - 1e-9:
                yield s.copy()
                next_out += output_every
