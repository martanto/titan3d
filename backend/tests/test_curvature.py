"""Bed-curvature term."""

import numpy as np

from titan3d.core.params import G
from titan3d.core.terrain import inclined_plane
from titan3d.core.curvature import bed_geometry, normal_gravity


def test_plane_has_zero_curvature() -> None:
    grid = inclined_plane(n=32, dx=10.0, slope_deg=25.0)
    geom = bed_geometry(grid.b, grid.dx, curvature=True)
    for k in (geom.bxx, geom.bxy, geom.byy):
        assert np.abs(k).max() < 1e-12
    u = np.full_like(grid.b, 20.0)
    g = normal_gravity(geom, u, u)
    np.testing.assert_allclose(g, G * np.cos(np.radians(25.0)), rtol=1e-12)


def test_cylinder_bed_centripetal_term() -> None:
    radius, dx, n = 2000.0, 5.0, 81
    x = (np.arange(n) - n // 2) * dx
    X, _ = np.meshgrid(x, x)
    b = radius - np.sqrt(radius**2 - X**2)  # concave-up channel, axis along y
    geom = bed_geometry(b, dx, curvature=True)
    c = n // 2
    assert abs(geom.bxx[c, c] - 1.0 / radius) < 1e-6
    u = np.full_like(b, 30.0)
    v = np.zeros_like(b)
    g = normal_gravity(geom, u, v)
    assert abs(g[c, c] - (G + 30.0**2 / radius)) < 1e-3
    # flow along the channel axis feels no centripetal term
    g_axis = normal_gravity(geom, v, u)
    assert abs(g_axis[c, c] - G) < 1e-9


def test_convex_crest_clamps_at_zero() -> None:
    radius, dx, n = 200.0, 2.0, 41
    x = (np.arange(n) - n // 2) * dx
    X, _ = np.meshgrid(x, x)
    b = np.sqrt(radius**2 - X**2)  # convex crest
    geom = bed_geometry(b, dx, curvature=True)
    u = np.full_like(b, 100.0)  # u²/R = 50 > g: material would lift off
    g = normal_gravity(geom, u, np.zeros_like(b))
    assert g.min() == 0.0
