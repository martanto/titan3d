"""Numba versions of the flux kernels in :mod:`titan3d.core.numerics`.

Each line (row for the x-sweep, column for the y-sweep) is processed by one
thread. The arithmetic follows the NumPy reference operation by operation, so
float64 results agree to round-off (verified in ``tests/test_numba_parity.py``).
"""

import math

import numpy as np
from numba import njit, prange

from titan3d.core.params import G, FloatArray
from titan3d.core.numerics import GHOST


@njit(inline="always", cache=True)
def _minmod(a: float, b: float) -> float:
    if a * b > 0.0:
        s = 1.0 if a > 0.0 else -1.0
        return s * min(abs(a), abs(b))
    return 0.0


@njit(inline="always", cache=True)
def _vel(h: float, q: float, h_dry: float) -> float:
    return q / max(h, h_dry) if h > h_dry else 0.0


@njit(cache=True)
def _line(H, B, QN, QT, K, dx, h_dry, dh, dqn, dqt):  # noqa: ANN001, ANN202
    """One padded line (length n + 4) → updates of length n; returns boundary fluxes."""
    n = H.shape[0] - 4
    m = n + 2  # reconstructed cells (padded indices 1 .. n+2)
    hm = np.empty(m)
    hp = np.empty(m)
    bm = np.empty(m)
    bp = np.empty(m)
    um = np.empty(m)
    up = np.empty(m)
    vm = np.empty(m)
    vp = np.empty(m)
    for c in range(m):
        p = c + 1
        h0, h1, h2 = H[p - 1], H[p], H[p + 1]
        u0 = _vel(h0, QN[p - 1], h_dry)
        u1 = _vel(h1, QN[p], h_dry)
        u2 = _vel(h2, QN[p + 1], h_dry)
        v0 = _vel(h0, QT[p - 1], h_dry)
        v1 = _vel(h1, QT[p], h_dry)
        v2 = _vel(h2, QT[p + 1], h_dry)
        sh = _minmod(h1 - h0, h2 - h1)
        su = _minmod(u1 - u0, u2 - u1)
        sv = _minmod(v1 - v0, v2 - v1)
        hm[c] = h1 - 0.5 * sh
        hp[c] = h1 + 0.5 * sh
        sb = _minmod(B[p] - B[p - 1], B[p + 1] - B[p])
        bm[c] = B[p] - 0.5 * sb
        bp[c] = B[p] + 0.5 * sb
        um[c] = u1 - 0.5 * su
        up[c] = u1 + 0.5 * su
        vm[c] = v1 - 0.5 * sv
        vp[c] = v1 + 0.5 * sv

    F1 = np.empty(n + 1)
    F2l = np.empty(n + 1)
    F2r = np.empty(n + 1)
    F3 = np.empty(n + 1)
    for k in range(n + 1):
        hL, hR = hp[k], hm[k + 1]
        bL, bR = bp[k], bm[k + 1]
        uL, uR = up[k], um[k + 1]
        vL, vR = vp[k], vm[k + 1]
        kL, kR = K[k + 1], K[k + 2]
        bstar = max(bL, bR)
        hLs = max(0.0, hL + bL - bstar)
        hRs = max(0.0, hR + bR - bstar)
        f1L = hLs * uL
        f1R = hRs * uR
        f2L = hLs * uL * uL + 0.5 * kL * G * hLs * hLs
        f2R = hRs * uR * uR + 0.5 * kR * G * hRs * hRs
        f3L = hLs * uL * vL
        f3R = hRs * uR * vR
        a = max(abs(uL) + math.sqrt(kL * G * hLs), abs(uR) + math.sqrt(kR * G * hRs))
        F1[k] = 0.5 * (f1L + f1R) - 0.5 * a * (hRs - hLs)
        f2 = 0.5 * (f2L + f2R) - 0.5 * a * (hRs * uR - hLs * uL)
        F3[k] = 0.5 * (f3L + f3R) - 0.5 * a * (hRs * vR - hLs * vL)
        F2l[k] = f2 + 0.5 * kL * G * (hL * hL - hLs * hLs)
        F2r[k] = f2 + 0.5 * kR * G * (hR * hR - hRs * hRs)

    for i in range(n):
        dh[i] = -(F1[i + 1] - F1[i]) / dx
        q = -(F2l[i + 1] - F2r[i]) / dx
        c = i + 1
        dqn[i] = q - G * 0.5 * (hm[c] + hp[c]) * (bp[c] - bm[c]) / dx
        dqt[i] = -(F3[i + 1] - F3[i]) / dx
    return F1[0], F1[n]


@njit(parallel=True, cache=True)
def _rhs(H, B, HU, HV, K, dx, h_dry):  # noqa: ANN001, ANN202
    g = 2
    nj, ni = H.shape[0] - 2 * g, H.shape[1] - 2 * g
    dt = H.dtype
    dh_x = np.empty((nj, ni), dtype=dt)
    dhu_x = np.empty((nj, ni), dtype=dt)
    dhv_x = np.empty((nj, ni), dtype=dt)
    dh_y = np.empty((ni, nj), dtype=dt)
    dhv_y = np.empty((ni, nj), dtype=dt)
    dhu_y = np.empty((ni, nj), dtype=dt)
    fw = np.empty(nj)
    fe = np.empty(nj)
    fs = np.empty(ni)
    fn = np.empty(ni)
    for r in prange(nj):
        j = r + g
        lo, hi = _line(
            H[j, :],
            B[j, :],
            HU[j, :],
            HV[j, :],
            K[j, :],
            dx,
            h_dry,
            dh_x[r],
            dhu_x[r],
            dhv_x[r],
        )
        fw[r] = lo
        fe[r] = hi
    for c in prange(ni):
        i = c + g
        lo, hi = _line(
            H[:, i],
            B[:, i],
            HV[:, i],
            HU[:, i],
            K[:, i],
            dx,
            h_dry,
            dh_y[c],
            dhv_y[c],
            dhu_y[c],
        )
        fs[c] = lo
        fn[c] = hi
    dh = dh_x + dh_y.T
    dhu = dhu_x + dhu_y.T
    dhv = dhv_x + dhv_y.T
    return dh, dhu, dhv, fw, fe, fs, fn


def rhs_block_numba(
    H: FloatArray,
    B: FloatArray,
    HU: FloatArray,
    HV: FloatArray,
    K: FloatArray,
    dx: float,
    h_dry: float,
) -> tuple[FloatArray, FloatArray, FloatArray, list[FloatArray]]:
    """Drop-in replacement for :func:`titan3d.core.numerics.rhs_block`.

    Arithmetic is done in float64 scalars; outputs keep the input dtype.
    """
    assert GHOST == 2
    dh, dhu, dhv, fw, fe, fs, fn = _rhs(H, B, HU, HV, K, float(dx), float(h_dry))
    return dh, dhu, dhv, [fw, fe, fs, fn]


@njit(parallel=True, cache=True)
def earth_pressure_numba(H, HU, HV, dx, hydrostatic, k_act, k_pas, h_dry):  # noqa: ANN001, ANN201
    """Numba version of :func:`titan3d.core.rheology.earth_pressure_block`."""
    nj, ni = H.shape
    K = np.empty((nj, ni), dtype=H.dtype)
    if hydrostatic:
        K[:] = 1.0
        return K
    for j in prange(nj):
        for i in range(ni):
            if j == 0 or i == 0 or j == nj - 1 or i == ni - 1:
                K[j, i] = k_act
                continue
            ue = _vel(H[j, i + 1], HU[j, i + 1], h_dry)
            uw = _vel(H[j, i - 1], HU[j, i - 1], h_dry)
            vn = _vel(H[j + 1, i], HV[j + 1, i], h_dry)
            vs = _vel(H[j - 1, i], HV[j - 1, i], h_dry)
            div = (ue - uw) / (2.0 * dx) + (vn - vs) / (2.0 * dx)
            K[j, i] = k_act if div >= 0.0 else k_pas
    return K


@njit(parallel=True, cache=True)
def friction_numba(  # noqa: ANN201
    h,
    hu,
    hv,
    dt,
    cos,
    bxx,
    bxy,
    byy,
    curvature,
    voellmy,
    tan_bed,
    mu,
    xi,
    h_dry,  # noqa: ANN001
):
    """Numba version of :func:`titan3d.core.rheology.apply_friction` (returns new arrays)."""
    nj, ni = h.shape
    hu_o = np.empty_like(hu)
    hv_o = np.empty_like(hv)
    for j in prange(nj):
        for i in range(ni):
            hh = h[j, i]
            if hh <= h_dry:
                hu_o[j, i] = 0.0
                hv_o[j, i] = 0.0
                continue
            qx, qy = hu[j, i], hv[j, i]
            mag = math.hypot(qx, qy)
            u = qx / max(hh, h_dry)
            v = qy / max(hh, h_dry)
            if curvature:
                acc = u * u * bxx[j, i] + 2.0 * u * v * bxy[j, i]
                acc = acc + v * v * byy[j, i]
                g_eff = max(cos[j, i] * (G + acc), 0.0)
            else:
                g_eff = G * cos[j, i]
            if voellmy:
                resist = hh * g_eff * mu + G * (u * u + v * v) / xi
            else:
                resist = hh * g_eff * tan_bed
            new = max(mag - dt * resist, 0.0)
            scale = new / max(mag, 1e-30) if mag > 0 else 0.0
            hu_o[j, i] = qx * scale
            hv_o[j, i] = qy * scale
    return hu_o, hv_o


@njit(parallel=True, cache=True)
def max_speed_numba(h, hu, hv, k_max, h_dry):  # noqa: ANN001, ANN201
    """Largest ``|u| + c`` and ``|v| + c`` over a window."""
    nj, ni = h.shape
    best = np.zeros(nj)
    for j in prange(nj):
        m = 0.0
        for i in range(ni):
            hh = h[j, i]
            c = math.sqrt(k_max * G * hh)
            u = abs(_vel(hh, hu[j, i], h_dry)) + c
            v = abs(_vel(hh, hv[j, i], h_dry)) + c
            m = max(m, u, v)
        best[j] = m
    return best.max()


@njit(parallel=True, cache=True)
def update_max_numba(h, hu, hv, h_max, u_max, h_dry):  # noqa: ANN001, ANN201
    """In-place running maxima of depth and speed over a window."""
    nj, ni = h.shape
    for j in prange(nj):
        for i in range(ni):
            hh = h[j, i]
            if hh > h_max[j, i]:
                h_max[j, i] = hh
            s = _vel(hh, math.hypot(hu[j, i], hv[j, i]), h_dry)
            if s > u_max[j, i]:
                u_max[j, i] = s


@njit(cache=True)
def wet_box_numba(h, j0, i0):  # noqa: ANN001, ANN201
    """Bounding box (end-exclusive, absolute) of ``h > 0`` in a window at ``(j0, i0)``."""
    nj, ni = h.shape
    jmin, jmax, imin, imax = nj, -1, ni, -1
    for j in range(nj):
        for i in range(ni):
            if h[j, i] > 0.0:
                if j < jmin:
                    jmin = j
                if j > jmax:
                    jmax = j
                if i < imin:
                    imin = i
                if i > imax:
                    imax = i
    if jmax < 0:
        return -1, -1, -1, -1
    return j0 + jmin, j0 + jmax + 1, i0 + imin, i0 + imax + 1
