"""NumPy reference kernels for the finite-volume flux update.

Scheme (per direction, dimension-by-dimension):

* MUSCL reconstruction with a minmod limiter of ``h``, ``b``, ``u``, ``v``
* Hydrostatic reconstruction (Audusse et al., 2004): well-balanced bed term, ``h ≥ 0``
* Rusanov (local Lax–Friedrichs) interface flux with earth-pressure coefficient ``k``

All kernels operate on *padded blocks*: arrays with two ghost cells on every
side, so the same code serves the full domain and the active window. The
Numba kernels in :mod:`titan3d.core.kernels_numba` reproduce these exactly.
"""

import numpy as np

from titan3d.core.params import G, FloatArray


GHOST = 2
"""Ghost cells required on each side of a block by the MUSCL stencil."""


def minmod(a: FloatArray, b: FloatArray) -> FloatArray:
    """Minmod slope limiter."""
    return np.where(a * b > 0.0, np.sign(a) * np.minimum(np.abs(a), np.abs(b)), 0.0)


def velocity(h: FloatArray, q: FloatArray, h_dry: float) -> FloatArray:
    """Velocity ``q / h``, zero where ``h <= h_dry``."""
    return np.where(h > h_dry, q / np.maximum(h, h_dry), 0.0)


def sweep(
    H: FloatArray,
    B: FloatArray,
    QN: FloatArray,
    QT: FloatArray,
    K: FloatArray,
    dx: float,
    h_dry: float,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    """Flux-divergence update along the last axis.

    Inputs have shape ``(m, n + 4)``: ``n`` interior cells with two ghost cells
    each side along the last axis.

    Args:
        H: Depth.
        B: Bed elevation.
        QN: Momentum normal to the interfaces (along the sweep axis).
        QT: Momentum tangential to the interfaces.
        K: Earth-pressure coefficient.
        dx: Cell size [m].
        h_dry: Dry threshold [m].

    Returns:
        ``(dh, dqn, dqt, f_lo, f_hi)``: time derivatives of shape ``(m, n)``
        and the mass flux through the first and last interfaces, shape ``(m,)``
        (used for outflow accounting at domain boundaries).
    """
    U = velocity(H, QN, h_dry)
    V = velocity(H, QT, h_dry)

    def centre_and_slope(A: FloatArray) -> tuple[FloatArray, FloatArray]:
        c = A[:, 1:-1]
        return c, minmod(c - A[:, :-2], A[:, 2:] - c)

    # cells 1 .. n+2 of the padded block (one neighbour each side)
    Hc, sH = centre_and_slope(H)
    Bc, sB = centre_and_slope(B)
    Uc, sU = centre_and_slope(U)
    Vc, sV = centre_and_slope(V)
    Kc = K[:, 1:-1]

    hm, hp = Hc - 0.5 * sH, Hc + 0.5 * sH  # minus / plus faces of each cell
    # Depth and bed are reconstructed separately. For a wet lake at rest the
    # depth slope is exactly minus the bed slope (minmod is odd), so faces keep
    # η constant; unlike η-reconstruction, dry neighbours never inherit a wet
    # cell's free surface, which would wall in thin flows on steep slopes
    # (Delestre et al., 2012).
    bm, bp = Bc - 0.5 * sB, Bc + 0.5 * sB
    um, up = Uc - 0.5 * sU, Uc + 0.5 * sU
    vm, vp = Vc - 0.5 * sV, Vc + 0.5 * sV

    # n + 1 interfaces between consecutive reconstructed cells
    hL, hR = hp[:, :-1], hm[:, 1:]
    bL, bR = bp[:, :-1], bm[:, 1:]
    uL, uR = up[:, :-1], um[:, 1:]
    vL, vR = vp[:, :-1], vm[:, 1:]
    kL, kR = Kc[:, :-1], Kc[:, 1:]

    bstar = np.maximum(bL, bR)
    hLs = np.maximum(0.0, hL + bL - bstar)
    hRs = np.maximum(0.0, hR + bR - bstar)

    f1L = hLs * uL
    f1R = hRs * uR
    f2L = hLs * uL * uL + 0.5 * kL * G * hLs * hLs
    f2R = hRs * uR * uR + 0.5 * kR * G * hRs * hRs
    f3L = hLs * uL * vL
    f3R = hRs * uR * vR
    a = np.maximum(
        np.abs(uL) + np.sqrt(kL * G * hLs), np.abs(uR) + np.sqrt(kR * G * hRs)
    )
    F1 = 0.5 * (f1L + f1R) - 0.5 * a * (hRs - hLs)
    F2 = 0.5 * (f2L + f2R) - 0.5 * a * (hRs * uR - hLs * uL)
    F3 = 0.5 * (f3L + f3R) - 0.5 * a * (hRs * vR - hLs * vL)

    # hydrostatic-reconstruction corrections: flux seen by left / right cell
    F2_left = F2 + 0.5 * kL * G * (hL * hL - hLs * hLs)
    F2_right = F2 + 0.5 * kR * G * (hR * hR - hRs * hRs)

    dh = -(F1[:, 1:] - F1[:, :-1]) / dx
    dqn = -(F2_left[:, 1:] - F2_right[:, :-1]) / dx
    dqt = -(F3[:, 1:] - F3[:, :-1]) / dx

    # centred bed-slope term inside each interior cell
    hm_i, hp_i = hm[:, 1:-1], hp[:, 1:-1]
    bm_i, bp_i = bm[:, 1:-1], bp[:, 1:-1]
    dqn = dqn - G * 0.5 * (hm_i + hp_i) * (bp_i - bm_i) / dx
    return dh, dqn, dqt, F1[:, 0], F1[:, -1]


def rhs_block(
    H: FloatArray,
    B: FloatArray,
    HU: FloatArray,
    HV: FloatArray,
    K: FloatArray,
    dx: float,
    h_dry: float,
) -> tuple[FloatArray, FloatArray, FloatArray, list[FloatArray]]:
    """Flux divergence on a padded block, both directions.

    Args:
        H, B, HU, HV, K: Padded arrays of shape ``(nj + 4, ni + 4)``.
        dx: Cell size [m].
        h_dry: Dry threshold [m].

    Returns:
        ``(dh, dhu, dhv, flux)`` where the derivatives have shape ``(nj, ni)``
        and ``flux = [west, east, south, north]`` holds the boundary mass-flux
        profiles (positive = towards +x / +y), each per unit length.
    """
    g = GHOST
    r = (slice(g, -g), slice(None))
    dh_x, dhu_x, dhv_x, fw, fe = sweep(H[r], B[r], HU[r], HV[r], K[r], dx, h_dry)
    c = (slice(None), slice(g, -g))
    dh_y, dhv_y, dhu_y, fs, fn = sweep(
        H[c].T, B[c].T, HV[c].T, HU[c].T, K[c].T, dx, h_dry
    )
    return (
        dh_x + dh_y.T,
        dhu_x + dhu_y.T,
        dhv_x + dhv_y.T,
        [fw, fe, fs, fn],
    )
