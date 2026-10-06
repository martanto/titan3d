"""Bed geometry: slope cosine and second derivatives for the curvature term.

A particle moving with plan-view velocity ``(u, v)`` over the bed ``z = b(x, y)``
has vertical acceleration ``u² b_xx + 2 u v b_xy + v² b_yy``. Its bed-normal
component adds to gravity in the normal stress (Titan2D's centripetal term)::

    g_eff = cosθ · (g + u² b_xx + 2 u v b_xy + v² b_yy)     clamped at ≥ 0

so flow is pressed harder into concave bends and lightened over convex breaks.
"""

from dataclasses import dataclass

import numpy as np

from titan3d.core.params import G, FloatArray


@dataclass(frozen=True)
class BedGeometry:
    """Per-cell slope and curvature of the bed.

    Attributes:
        cos_theta: Cosine of the bed slope angle.
        bxx: ∂²b/∂x² [1/m] (zeros when curvature is disabled).
        bxy: ∂²b/∂x∂y [1/m].
        byy: ∂²b/∂y² [1/m].
        curvature: Whether the curvature term is active.
    """

    cos_theta: FloatArray
    bxx: FloatArray
    bxy: FloatArray
    byy: FloatArray
    curvature: bool


def bed_geometry(b: FloatArray, dx: float, curvature: bool = True) -> BedGeometry:
    """Compute slope cosine and (optionally) bed second derivatives.

    Args:
        b: Bed elevation ``[j, i]`` [m].
        dx: Cell size [m].
        curvature: Compute second derivatives; zeros otherwise.

    Returns:
        Bed geometry arrays in the dtype of ``b``.
    """
    by, bx = np.gradient(b, dx)
    cos_theta = (1.0 / np.sqrt(1.0 + bx**2 + by**2)).astype(b.dtype)
    if curvature:
        bxy, bxx = np.gradient(bx, dx)
        byy, _ = np.gradient(by, dx)
    else:
        bxx = bxy = byy = np.zeros_like(b)
    return BedGeometry(
        cos_theta=cos_theta,
        bxx=bxx.astype(b.dtype),
        bxy=bxy.astype(b.dtype),
        byy=byy.astype(b.dtype),
        curvature=curvature,
    )


def normal_gravity(
    geom: BedGeometry,
    u: FloatArray,
    v: FloatArray,
    window: tuple[slice, slice] = (slice(None), slice(None)),
) -> FloatArray:
    """Effective bed-normal gravity ``g_eff`` on a window [m/s²]."""
    cos = geom.cos_theta[window]
    if not geom.curvature:
        return G * cos
    acc = u * u * geom.bxx[window] + 2.0 * u * v * geom.bxy[window]
    acc = acc + v * v * geom.byy[window]
    return np.maximum(cos * (G + acc), 0.0)
