"""Opt-in one-level MUSCL finite-volume solver on a shared leaf-face mesh."""

from collections.abc import Sequence

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
from titan3d.core.solver import Solver
from titan3d.core.amr_mesh import LeafMesh, dilate
from titan3d.core.numerics import velocity
from titan3d.core.rheology import earth_pressure_coefficients


def scatter_faces(left, right, lr, rr, length, area, f1, f2l, f2r, f3, axis):
    """NumPy reference accumulation; each shared flux has opposite owners."""
    n = len(area)
    result = np.empty((3, n))
    for k in range(3):
        if k == 0:
            fl = fr = f1
        elif k == 1:
            fl, fr = np.where(axis == 0, f2l, f3), np.where(axis == 0, f2r, f3)
        else:
            fl, fr = np.where(axis == 1, f2l, f3), np.where(axis == 1, f2r, f3)
        result[k] = (
            np.bincount(right, weights=fr * length * rr, minlength=n)
            - np.bincount(left, weights=fl * length * lr, minlength=n)
        ) / area
    out = float(np.sum(f1 * length * (lr.astype(np.int64) - rr.astype(np.int64))))
    return result, out


def scatter_faces_loop(left, right, lr, rr, length, area, f1, f2l, f2r, f3, axis):
    """Loop form compiled by Numba; kept independent of Python mesh objects."""
    result = np.zeros((3, len(area)))
    out = 0.0
    for f in range(len(left)):
        left_id, r = left[f], right[f]
        if lr[f]:
            result[0, left_id] -= f1[f] * length[f] / area[left_id]
            result[1, left_id] -= (
                (f2l[f] if axis[f] == 0 else f3[f]) * length[f] / area[left_id]
            )
            result[2, left_id] -= (
                (f2l[f] if axis[f] == 1 else f3[f]) * length[f] / area[left_id]
            )
        else:
            out -= f1[f] * length[f]
        if rr[f]:
            result[0, r] += f1[f] * length[f] / area[r]
            result[1, r] += (f2r[f] if axis[f] == 0 else f3[f]) * length[f] / area[r]
            result[2, r] += (f2r[f] if axis[f] == 1 else f3[f]) * length[f] / area[r]
        else:
            out += f1[f] * length[f]
    return result, out


def neighbour_derivatives(field, left, right, length, width, axis):
    """Compiled neighbour differences; yields minmod and centred derivatives."""
    lo = np.zeros((2, len(width)))
    hi = np.zeros((2, len(width)))
    for face in range(len(left)):
        left_id, right_id = left[face], right[face]
        direction = axis[face]
        difference = (
            (field[right_id] - field[left_id])
            * length[face]
            / ((width[left_id] + width[right_id]) / 2)
        )
        lo[direction, right_id] += difference / width[right_id]
        hi[direction, left_id] += difference / width[left_id]
    limited = np.zeros_like(lo)
    for direction in range(2):
        for cell in range(len(width)):
            a, b = lo[direction, cell], hi[direction, cell]
            if a * b > 0:
                limited[direction, cell] = min(a, b) if a > 0 else max(a, b)
    return limited, 0.5 * (lo + hi)


class AdaptiveSolver(Solver):
    """Two cell sizes, one shared time step; uniform-grid-compatible outputs.

    The grid spacing is the finest spacing, not the parent-cell spacing.
    ``fixed_refinement`` is a verification hook; production adapts dynamically.
    Dense terrain/output storage is retained in this initial implementation.
    """

    def __init__(
        self,
        grid: Grid,
        params: FlowParams | None = None,
        flux_sources: Sequence[FluxSource] = (),
        track_max: bool = True,
        fixed_refinement: np.ndarray | None = None,
    ):
        super().__init__(grid, params, flux_sources, track_max)
        self.fixed_refinement = fixed_refinement
        shape = ((self.ny + 1) // 2, (self.nx + 1) // 2)
        self.cooldown = np.zeros(shape, dtype=np.int64)
        self.mesh = LeafMesh(
            grid,
            np.zeros(shape, dtype=bool)
            if fixed_refinement is None
            else fixed_refinement,
        )
        self.regrids = 0
        self.leaf_min = self.mesh.n
        self.leaf_max = self.mesh.n
        self.last_regrid_step = -1
        self.scatter = scatter_faces
        self.derivatives = None
        if self.backend == Backend.NUMBA:
            from numba import njit

            self.scatter = njit(cache=True, fastmath=False)(scatter_faces_loop)
            self.derivatives = njit(cache=True, fastmath=False)(neighbour_derivatives)
        self._geometry()

    def _geometry(self) -> None:
        self.b_slopes = np.array(self.mesh.slopes(self.mesh.b))
        self.leaf_geometry = tuple(
            self.mesh.restrict(a)
            for a in (self.geom.cos_theta, self.geom.bxx, self.geom.bxy, self.geom.byy)
        )

    def _blocks(self, a: FloatArray, how: str) -> FloatArray:
        padded = np.pad(a, ((0, self.ny % 2), (0, self.nx % 2)), mode="edge")
        blocks = padded.reshape((self.ny + 1) // 2, 2, (self.nx + 1) // 2, 2)
        return blocks.max(axis=(1, 3)) if how == "max" else blocks.min(axis=(1, 3))

    def refinement_indicator(self, s: State) -> np.ndarray:
        """Tag fronts and relative depth/velocity variation, and pin vents."""
        high, low = self._blocks(s.h, "max"), self._blocks(s.h, "min")
        # Also detect gradients between neighbouring parent cells.
        padded = np.pad(high, 1, mode="edge")
        around_hi = np.maximum.reduce(
            [
                padded[dj : dj + high.shape[0], di : di + high.shape[1]]
                for dj, di in ((0, 1), (1, 0), (1, 1), (1, 2), (2, 1))
            ]
        )
        around_lo = np.minimum.reduce(
            [
                padded[dj : dj + high.shape[0], di : di + high.shape[1]]
                for dj, di in ((0, 1), (1, 0), (1, 1), (1, 2), (2, 1))
            ]
        )
        variation = np.maximum(high - low, around_hi - around_lo)
        tag = (around_hi > self.p.h_dry) & (
            (around_lo <= self.p.h_dry)
            | (variation > self.p.amr_gradient * np.maximum(around_hi, self.p.h_dry))
        )
        speed = velocity(s.h, np.hypot(s.hu, s.hv), self.p.h_dry)
        vmax, vmin = self._blocks(speed, "max"), self._blocks(speed, "min")
        tag |= (vmax - vmin) > self.p.amr_gradient * np.maximum(vmax, 1.0)
        source_mask = np.zeros_like(s.h, dtype=bool)
        for f in self.sources.footprints:
            source_mask[f.window] |= f.profile > 0
        tag |= self._blocks(source_mask, "max")
        return dilate(tag, self.p.amr_buffer)

    def regrid(self, s: State, refined: np.ndarray | None = None) -> None:
        """Conservatively change ownership between complete RK steps."""
        if refined is None:
            refined = self.fixed_refinement
        if refined is None:
            tag = self.refinement_indicator(s)
            self.cooldown = np.where(
                tag, self.p.amr_coarsen_delay, np.maximum(self.cooldown - 1, 0)
            )
            refined = tag | (self.cooldown > 0)
        self.last_regrid_step = s.step
        refined = refined.copy()
        if self.ny % 2:
            refined[-1, :] = True
        if self.nx % 2:
            refined[:, -1] = True
        if np.array_equal(refined, self.mesh.refined):
            return
        new = LeafMesh(self.grid, refined)
        # The state raster is already a conservative representation of old leaves.
        h, hu, hv = (new.restrict(a) for a in (s.h, s.hu, s.hv))
        self.mesh = new
        self._geometry()
        s.h[:], s.hu[:], s.hv[:] = self.mesh.raster(h, hu, hv)
        self.regrids += 1
        self.leaf_min = min(self.leaf_min, new.n)
        self.leaf_max = max(self.leaf_max, new.n)
        self._maxima(s)

    def initial_state(self, h0: FloatArray) -> State:
        """Initialise on the finest raster, then conservatively adapt."""
        s = super().initial_state(h0)
        self.regrid(s)
        # Also project when a fixed mesh was supplied at construction.
        leaves = tuple(self.mesh.restrict(a) for a in (s.h, s.hu, s.hv))
        s.h[:], s.hu[:], s.hv[:] = self.mesh.raster(*leaves)
        self._maxima(s)
        return s

    def _maxima(self, s: State) -> None:
        if self.track_max:
            np.maximum(self.h_max, s.h, out=self.h_max)
            speed = velocity(s.h, np.hypot(s.hu, s.hv), self.p.h_dry)
            np.maximum(self.u_max, speed, out=self.u_max)

    def max_dt(self, s: State) -> float:
        """Unsplit CFL bound over every leaf, including both wave directions."""
        m = self.mesh
        h, hu, hv = (m.restrict(a) for a in (s.h, s.hu, s.hv))
        speed = np.abs(velocity(h, hu, self.p.h_dry)) + np.abs(
            velocity(h, hv, self.p.h_dry)
        )
        speed += 2 * np.sqrt(self.k_max * G * h)
        wet = speed > 0
        return (
            float(np.min(self.p.cfl * m.width[wet] / speed[wet]))
            if wet.any()
            else np.inf
        )

    def _friction(self, h, hu, hv, dt):
        u, v = velocity(h, hu, self.p.h_dry), velocity(h, hv, self.p.h_dry)
        cos, bxx, bxy, byy = self.leaf_geometry
        gravity = np.maximum(cos * (G + u * u * bxx + 2 * u * v * bxy + v * v * byy), 0)
        resist = (
            h * gravity * self.p.mu + G * (u * u + v * v) / self.p.xi
            if self.p.rheology == Rheology.VOELLMY
            else h * gravity * self.tan_bed
        )
        magnitude = np.hypot(hu, hv)
        factor = np.maximum(magnitude - dt * resist, 0) / np.maximum(magnitude, 1e-30)
        factor[h <= self.p.h_dry] = 0
        return hu * factor, hv * factor

    def leaf_rhs(self, h, hu, hv, dt):
        """MUSCL + hydrostatic shared-face flux, with a draining limiter."""
        m = self.mesh
        u, v = velocity(h, hu, self.p.h_dry), velocity(h, hv, self.p.h_dry)
        if self.derivatives is not None:
            h_grad, _ = self.derivatives(h, m.left, m.right, m.length, m.width, m.axis)
            u_grad, u_centred = self.derivatives(
                u, m.left, m.right, m.length, m.width, m.axis
            )
            v_grad, v_centred = self.derivatives(
                v, m.left, m.right, m.length, m.width, m.axis
            )
            div = u_centred[0] + v_centred[1]
        else:
            h_grad, u_grad, v_grad = (np.array(m.slopes(a)) for a in (h, u, v))
            div = m.divergence(u, v)
        if self.p.earth_pressure == EarthPressure.HYDROSTATIC:
            k = np.ones_like(h)
        else:
            ka, kp = earth_pressure_coefficients(self.p.phi_int_deg, self.p.phi_bed_deg)
            k = np.where(div >= 0, ka, kp)
        gradients = [h_grad, self.b_slopes, u_grad, v_grad]
        active = (h[m.left] > 0) | (h[m.right] > 0)
        left_id, r, axis = m.left[active], m.right[active], m.axis[active]
        left_real, right_real, length = (
            m.left_real[active],
            m.right_real[active],
            m.length[active],
        )
        values = []
        for a, grad in zip((h, m.b, u, v), gradients, strict=True):
            al = a[left_id] + 0.5 * m.width[left_id] * grad[axis, left_id] * left_real
            ar = a[r] - 0.5 * m.width[r] * grad[axis, r] * right_real
            values.append((al, ar))
        (hl, hr), (bl, br), (ul, ur), (vl, vr) = values
        hl, hr = np.maximum(hl, 0), np.maximum(hr, 0)
        un_l, un_r = np.where(axis == 0, ul, vl), np.where(axis == 0, ur, vr)
        ut_l, ut_r = np.where(axis == 0, vl, ul), np.where(axis == 0, vr, ur)
        bs = np.maximum(bl, br)
        hs_l, hs_r = np.maximum(hl + bl - bs, 0), np.maximum(hr + br - bs, 0)
        kl, kr = k[left_id], k[r]
        wave = np.maximum(
            np.abs(un_l) + np.sqrt(kl * G * hs_l), np.abs(un_r) + np.sqrt(kr * G * hs_r)
        )
        f1 = 0.5 * (hs_l * un_l + hs_r * un_r - wave * (hs_r - hs_l))
        f2 = 0.5 * (
            hs_l * un_l**2
            + hs_r * un_r**2
            + 0.5 * G * (kl * hs_l**2 + kr * hs_r**2)
            - wave * (hs_r * un_r - hs_l * un_l)
        )
        f3 = 0.5 * (
            hs_l * un_l * ut_l + hs_r * un_r * ut_r - wave * (hs_r * ut_r - hs_l * ut_l)
        )
        outgoing = np.bincount(
            left_id, weights=np.maximum(f1, 0) * length * left_real, minlength=m.n
        ) + np.bincount(
            r, weights=np.maximum(-f1, 0) * length * right_real, minlength=m.n
        )
        theta = np.minimum(1, h * m.area / np.maximum(dt * outgoing, 1e-300))
        donor = np.where(
            f1 >= 0,
            np.where(left_real, theta[left_id], 1),
            np.where(right_real, theta[r], 1),
        )
        f1, f2, f3 = f1 * donor, f2 * donor, f3 * donor
        f2l = f2 + 0.5 * kl * G * (hl**2 - hs_l**2)
        f2r = f2 + 0.5 * kr * G * (hr**2 - hs_r**2)
        rhs, out = self.scatter(
            left_id,
            r,
            left_real,
            right_real,
            length,
            m.area,
            f1,
            f2l,
            f2r,
            f3,
            axis,
        )
        rhs[1] -= G * h * gradients[1][0]
        rhs[2] -= G * h * gradients[1][1]
        return rhs, out

    def step(self, s: State, dt: float) -> State:
        """Shared SSP-RK2 stages, followed by exact-time source integration."""
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError("Step duration must be finite and positive")
        if self.last_regrid_step != s.step and s.step % self.p.amr_regrid_every == 0:
            self.regrid(s)
        m = self.mesh
        h0, qx0, qy0 = (m.restrict(a).astype(self.dtype) for a in (s.h, s.hu, s.hv))
        rhs1, out1 = self.leaf_rhs(h0, qx0, qy0, dt)
        h1 = h0 + dt * rhs1[0]
        if h1.min() < -1e-12:
            raise FloatingPointError("Negative AMR Euler-stage depth")
        h1 = np.maximum(h1, 0)
        qx1, qy1 = self._friction(h1, qx0 + dt * rhs1[1], qy0 + dt * rhs1[2], dt)
        rhs2, out2 = self.leaf_rhs(h1, qx1, qy1, dt)
        h2 = 0.5 * (h0 + h1 + dt * rhs2[0])
        if h2.min() < -1e-12:
            raise FloatingPointError("Negative AMR RK-stage depth")
        h2 = np.maximum(h2, 0)
        qx2, qy2 = self._friction(
            h2,
            0.5 * (qx0 + qx1 + dt * rhs2[1]),
            0.5 * (qy0 + qy1 + dt * rhs2[2]),
            0.5 * dt,
        )
        s.h[:], s.hu[:], s.hv[:] = m.raster(h2, qx2, qy2)
        s.vol_out += 0.5 * dt * (out1 + out2)
        if self.sources:
            s.vol_source += self.sources.apply(s.h, s.hu, s.hv, s.t, s.t + dt)
        s.t += dt
        s.step += 1
        s.box = self.kernels.wet_box(s.h, 0, 0)
        self._maxima(s)
        # Adapt here so the next max_dt sees the new mesh before choosing dt.
        if s.step % self.p.amr_regrid_every == 0:
            self.regrid(s)
        return s
