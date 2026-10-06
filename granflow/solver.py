"""
granflow.solver
===============

Depth-averaged granular flow solver in the spirit of Titan2D
(Patra et al., 2005; Savage & Hutter, 1989).

Governing equations (Cartesian, plan-view coordinates on a DEM b(x, y)):

    h_t  + (hu)_x + (hv)_y = 0
    (hu)_t + (hu^2 + k g h^2 / 2)_x + (huv)_y = -g h b_x - F_x
    (hv)_t + (huv)_x + (hv^2 + k g h^2 / 2)_y = -g h b_y - F_y

with basal resistance F opposing the depth-averaged velocity:

    Coulomb   |F| = h g_n tan(phi_bed)                   (Titan2D default)
    Voellmy   |F| = h g_n mu + g |u|^2 / xi              (Titan2D "Voellmy-Salm")

g_n = g cos(theta) is the bed-normal gravity, k is the earth-pressure
coefficient (k = 1 is hydrostatic; Savage-Hutter k_act/k_pass optional).

Numerics
--------
* Finite volume, uniform grid, dimension splitting of fluxes
* MUSCL (minmod) reconstruction of h, eta = h + b, u, v
* Hydrostatic reconstruction (Audusse et al., 2004) -> well-balanced, h >= 0
* Rusanov (local Lax-Friedrichs) interface flux
* SSP-RK2 (Heun) time stepping with adaptive CFL time step
* Friction applied as an implicit stopping step: momentum magnitude is
  reduced by dt*|F| and clamped at zero, so material can come to rest
  on slopes flatter than the friction angle (the key Coulomb behaviour).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator

import numpy as np

G = 9.81


@dataclass
class FlowParams:
    rheology: str = "coulomb"        # "coulomb" | "voellmy"
    phi_bed_deg: float = 14.0        # basal friction angle (Coulomb)
    phi_int_deg: float = 30.0        # internal friction angle (for k_ap)
    mu: float = 0.12                 # Voellmy dry-friction coefficient
    xi: float = 1000.0               # Voellmy turbulence coefficient [m/s^2]
    earth_pressure: str = "hydrostatic"  # "hydrostatic" | "savage-hutter"
    cfl: float = 0.4
    h_dry: float = 1e-3              # depth below which a cell is treated as dry [m]


@dataclass
class State:
    h: np.ndarray
    hu: np.ndarray
    hv: np.ndarray
    t: float = 0.0
    step: int = 0


# ---------------------------------------------------------------- helpers
def _minmod(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.where(a * b > 0.0, np.sign(a) * np.minimum(np.abs(a), np.abs(b)), 0.0)


def _velocity(h, hq, h_dry):
    return np.where(h > h_dry, hq / np.maximum(h, h_dry), 0.0)


def earth_pressure_coeff(phi_int_deg: float, phi_bed_deg: float, divergence: np.ndarray) -> np.ndarray:
    """Savage-Hutter active/passive coefficient (isotropic approximation).

    Active (spreading, div u > 0) / passive (converging, div u < 0).
    """
    pi, pb = np.radians(phi_int_deg), np.radians(phi_bed_deg)
    c2i, c2b = np.cos(pi) ** 2, np.cos(pb) ** 2
    root = np.sqrt(max(1.0 - c2i / c2b, 0.0))
    k_act = 2.0 * (1.0 - root) / c2i - 1.0
    k_pas = 2.0 * (1.0 + root) / c2i - 1.0
    return np.where(divergence >= 0.0, k_act, k_pas)


class Solver:
    """Depth-averaged granular flow on a regular DEM grid.

    Parameters
    ----------
    b : (ny, nx) bed elevation [m]
    dx : grid spacing [m] (square cells)
    params : FlowParams
    """

    def __init__(self, b: np.ndarray, dx: float, params: FlowParams | None = None):
        self.b = np.asarray(b, dtype=np.float64)
        self.dx = float(dx)
        self.p = params or FlowParams()
        by, bx = np.gradient(self.b, self.dx)
        self.cos_theta = 1.0 / np.sqrt(1.0 + bx ** 2 + by ** 2)
        self.g_n = G * self.cos_theta
        self.tan_bed = np.tan(np.radians(self.p.phi_bed_deg))

    # ------------------------------------------------------------ fluxes
    def _dir_update(self, h, qn, qt, k, axis):
        """Return d/dt contribution of fluxes along `axis` for (h, qn, qt).

        qn is momentum normal to the interfaces (along axis), qt tangential.
        """
        p = self.p
        pad = [(0, 0), (0, 0)]
        pad[axis] = (2, 2)
        H = np.pad(h, pad, mode="edge")
        B = np.pad(self.b, pad, mode="edge")
        QN = np.pad(qn, pad, mode="edge")
        QT = np.pad(qt, pad, mode="edge")
        K = np.pad(k, pad, mode="edge")
        U = _velocity(H, QN, p.h_dry)
        V = _velocity(H, QT, p.h_dry)
        E = H + B

        def sl(a, lo, hi):
            """Slice along `axis` from lo to (len + hi) when hi <= 0."""
            idx = [slice(None), slice(None)]
            idx[axis] = slice(lo, a.shape[axis] + hi)
            return a[tuple(idx)]

        # cells with one ghost each side: index range 1..n+2 of padded
        def slopes(A):
            c = sl(A, 1, -1)
            return c, _minmod(c - sl(A, 0, -2), sl(A, 2, 0) - c)

        Hc, sH = slopes(H)
        Ec, sE = slopes(E)
        Uc, sU = slopes(U)
        Vc, sV = slopes(V)
        Kc = sl(K, 1, -1)

        hm, hp = Hc - 0.5 * sH, Hc + 0.5 * sH          # minus/plus faces of each cell
        em, ep = Ec - 0.5 * sE, Ec + 0.5 * sE
        bm, bp = em - hm, ep - hp                       # b at faces
        um, up = Uc - 0.5 * sU, Uc + 0.5 * sU
        vm, vp = Vc - 0.5 * sV, Vc + 0.5 * sV

        # interfaces between cell j (left, plus face) and j+1 (right, minus face)
        hL, hR = sl(hp, 0, -1), sl(hm, 1, 0)
        bL, bR = sl(bp, 0, -1), sl(bm, 1, 0)
        uL, uR = sl(up, 0, -1), sl(um, 1, 0)
        vL, vR = sl(vp, 0, -1), sl(vm, 1, 0)
        kL, kR = sl(Kc, 0, -1), sl(Kc, 1, 0)

        bstar = np.maximum(bL, bR)
        hLs = np.maximum(0.0, hL + bL - bstar)
        hRs = np.maximum(0.0, hR + bR - bstar)

        def phys(hh, uu, vv, kk):
            return hh * uu, hh * uu * uu + 0.5 * kk * G * hh * hh, hh * uu * vv

        f1L, f2L, f3L = phys(hLs, uL, vL, kL)
        f1R, f2R, f3R = phys(hRs, uR, vR, kR)
        a = np.maximum(np.abs(uL) + np.sqrt(kL * G * hLs), np.abs(uR) + np.sqrt(kR * G * hRs))
        F1 = 0.5 * (f1L + f1R) - 0.5 * a * (hRs - hLs)
        F2 = 0.5 * (f2L + f2R) - 0.5 * a * (hRs * uR - hLs * uL)
        F3 = 0.5 * (f3L + f3R) - 0.5 * a * (hRs * vR - hLs * vL)

        # hydrostatic-reconstruction corrections (left / right sided fluxes)
        F2_left = F2 + 0.5 * kL * G * (hL ** 2 - hLs ** 2)   # flux seen by left cell
        F2_right = F2 + 0.5 * kR * G * (hR ** 2 - hRs ** 2)  # flux seen by right cell

        # interior cells are 1..n of the "c" arrays -> interfaces 0..n
        n = h.shape[axis]
        def iface(A, lo, hi):
            idx = [slice(None), slice(None)]
            idx[axis] = slice(lo, hi)
            return A[tuple(idx)]

        # cell i (0..n-1) sits at c-index i+1; its right interface index i+1, left interface i
        dh = -(iface(F1, 1, n + 1) - iface(F1, 0, n)) / self.dx
        dqn = -(iface(F2_left, 1, n + 1) - iface(F2_right, 0, n)) / self.dx
        dqt = -(iface(F3, 1, n + 1) - iface(F3, 0, n)) / self.dx

        # second-order centred bed-slope term inside each cell
        hm_i, hp_i = iface(hm, 1, n + 1), iface(hp, 1, n + 1)
        bm_i, bp_i = iface(bm, 1, n + 1), iface(bp, 1, n + 1)
        dqn += -G * 0.5 * (hm_i + hp_i) * (bp_i - bm_i) / self.dx
        return dh, dqn, dqt

    def _rhs(self, h, hu, hv):
        p = self.p
        if p.earth_pressure == "savage-hutter":
            u, v = _velocity(h, hu, p.h_dry), _velocity(h, hv, p.h_dry)
            div = np.gradient(u, self.dx, axis=1) + np.gradient(v, self.dx, axis=0)
            k = earth_pressure_coeff(p.phi_int_deg, p.phi_bed_deg, div)
        else:
            k = np.ones_like(h)
        dh_x, dhu_x, dhv_x = self._dir_update(h, hu, hv, k, axis=1)
        dh_y, dhv_y, dhu_y = self._dir_update(h, hv, hu, k, axis=0)
        return dh_x + dh_y, dhu_x + dhu_y, dhv_x + dhv_y

    def _friction(self, h, hu, hv, dt):
        p = self.p
        mag = np.hypot(hu, hv)
        speed = np.where(h > p.h_dry, mag / np.maximum(h, p.h_dry), 0.0)
        if p.rheology == "voellmy":
            resist = h * self.g_n * p.mu + G * speed ** 2 / p.xi * h
        else:
            resist = h * self.g_n * self.tan_bed
        new = np.maximum(mag - dt * resist, 0.0)
        scale = np.where(mag > 0, new / np.maximum(mag, 1e-30), 0.0)
        hu, hv = hu * scale, hv * scale
        dry = h <= p.h_dry
        hu[dry] = 0.0
        hv[dry] = 0.0
        return hu, hv

    # ------------------------------------------------------------- step
    def max_dt(self, s: State) -> float:
        p = self.p
        u = _velocity(s.h, s.hu, p.h_dry)
        v = _velocity(s.h, s.hv, p.h_dry)
        c = np.sqrt(G * s.h)
        smax = max(float(np.max(np.abs(u) + c)), float(np.max(np.abs(v) + c)), 1e-6)
        return p.cfl * self.dx / smax

    def step(self, s: State, dt: float) -> State:
        h0, hu0, hv0 = s.h, s.hu, s.hv
        k1 = self._rhs(h0, hu0, hv0)
        h1 = np.maximum(h0 + dt * k1[0], 0.0)
        hu1, hv1 = hu0 + dt * k1[1], hv0 + dt * k1[2]
        hu1, hv1 = self._friction(h1, hu1, hv1, dt)
        k2 = self._rhs(h1, hu1, hv1)
        h2 = np.maximum(0.5 * (h0 + h1 + dt * k2[0]), 0.0)
        hu2 = 0.5 * (hu0 + hu1 + dt * k2[1])
        hv2 = 0.5 * (hv0 + hv1 + dt * k2[2])
        hu2, hv2 = self._friction(h2, hu2, hv2, 0.5 * dt)
        return State(h2, hu2, hv2, s.t + dt, s.step + 1)

    def run(self, s: State, t_end: float, output_every: float,
            callback: Callable[[State], None] | None = None) -> Iterator[State]:
        """Advance to t_end, yielding the state every `output_every` seconds."""
        next_out = s.t
        yield s
        next_out += output_every
        while s.t < t_end - 1e-9:
            dt = min(self.max_dt(s), next_out - s.t, t_end - s.t)
            s = self.step(s, dt)
            if callback:
                callback(s)
            if s.t >= next_out - 1e-9:
                yield s
                next_out += output_every
