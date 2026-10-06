"""Basal friction (Coulomb / Voellmy) and the Savage–Hutter earth-pressure coefficient."""

import numpy as np

from titan3d.core.params import G, Rheology, FloatArray, FlowParams, EarthPressure
from titan3d.core.numerics import velocity
from titan3d.core.curvature import BedGeometry, normal_gravity


def earth_pressure_coefficients(
    phi_int_deg: float, phi_bed_deg: float
) -> tuple[float, float]:
    """Savage–Hutter active and passive coefficients.

    Args:
        phi_int_deg: Internal friction angle [deg].
        phi_bed_deg: Basal friction angle [deg].

    Returns:
        ``(k_act, k_pas)``. When ``φ_bed > φ_int`` both collapse to one value.
    """
    c2i = np.cos(np.radians(phi_int_deg)) ** 2
    c2b = np.cos(np.radians(phi_bed_deg)) ** 2
    root = np.sqrt(max(1.0 - c2i / c2b, 0.0))
    k_act = 2.0 * (1.0 - root) / c2i - 1.0
    k_pas = 2.0 * (1.0 + root) / c2i - 1.0
    return float(k_act), float(k_pas)


def max_earth_pressure(p: FlowParams) -> float:
    """Largest ``k`` the model can produce (for the CFL wave speed)."""
    if p.earth_pressure == EarthPressure.HYDROSTATIC:
        return 1.0
    return max(earth_pressure_coefficients(p.phi_int_deg, p.phi_bed_deg))


def earth_pressure_block(
    H: FloatArray, HU: FloatArray, HV: FloatArray, dx: float, p: FlowParams
) -> FloatArray:
    """Earth-pressure coefficient on a padded block.

    Active where the flow spreads (``∇·u ≥ 0``), passive where it converges.
    Divergence uses centred differences; the outermost ghost ring is never read
    by the flux sweep and is left active.
    """
    if p.earth_pressure == EarthPressure.HYDROSTATIC:
        return np.ones_like(H)
    k_act, k_pas = earth_pressure_coefficients(p.phi_int_deg, p.phi_bed_deg)
    u = velocity(H, HU, p.h_dry)
    v = velocity(H, HV, p.h_dry)
    div = np.zeros_like(H)
    div[1:-1, 1:-1] = (u[1:-1, 2:] - u[1:-1, :-2]) / (2.0 * dx) + (
        v[2:, 1:-1] - v[:-2, 1:-1]
    ) / (2.0 * dx)
    return np.where(div >= 0.0, k_act, k_pas).astype(H.dtype)


def apply_friction(
    h: FloatArray,
    hu: FloatArray,
    hv: FloatArray,
    dt: float,
    geom: BedGeometry,
    window: tuple[slice, slice],
    p: FlowParams,
    tan_bed: float,
) -> tuple[FloatArray, FloatArray]:
    """Implicit stopping step for basal resistance.

    The momentum magnitude is reduced by ``dt · |F|`` and clamped at zero, so
    material comes to rest where the driving stress falls below the resistance.

    Resistance per unit area divided by density:

    * Coulomb: ``h g_eff tan φ_bed``
    * Voellmy: ``h g_eff μ + g |u|² / ξ``

    Args:
        h: Depth on the window.
        hu: x-momentum on the window.
        hv: y-momentum on the window.
        dt: Time step [s].
        geom: Bed geometry of the full grid.
        window: Slices of the window into the full grid.
        p: Flow parameters.
        tan_bed: ``tan φ_bed``.

    Returns:
        Updated ``(hu, hv)``.
    """
    mag = np.hypot(hu, hv)
    u = velocity(h, hu, p.h_dry)
    v = velocity(h, hv, p.h_dry)
    g_eff = normal_gravity(geom, u, v, window)
    if p.rheology == Rheology.VOELLMY:
        resist = h * g_eff * p.mu + G * (u * u + v * v) / p.xi
    else:
        resist = h * g_eff * tan_bed
    new = np.maximum(mag - dt * resist, 0.0)
    scale = np.where(mag > 0, new / np.maximum(mag, 1e-30), 0.0)
    hu = hu * scale
    hv = hv * scale
    dry = h <= p.h_dry
    hu[dry] = 0.0
    hv[dry] = 0.0
    return hu, hv
