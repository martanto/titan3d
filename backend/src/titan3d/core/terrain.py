"""Synthetic terrain for tests and demos."""

import numpy as np

from titan3d.core.grid import Grid


def synthetic_volcano(
    n: int = 256,
    dx: float = 25.0,
    height: float = 1700.0,
    base_r: float = 2600.0,
    crater_r: float = 260.0,
    breach_az_deg: float = 200.0,
    n_gullies: int = 9,
    crater_depth: float = 120.0,
    seed: int = 7,
) -> Grid:
    """Stratovolcano with a breached summit crater and radial gullies.

    Args:
        n: Grid size (n × n cells).
        dx: Cell size [m].
        height: Cone height above the apron [m].
        base_r: e-folding radius of the cone [m].
        crater_r: Summit crater radius [m].
        breach_az_deg: Azimuth of the crater breach, clockwise from north [deg].
        n_gullies: Number of radial erosional gullies.
        crater_depth: Depth of the crater bowl [m].
        seed: Random seed for gully phase and roughness.

    Returns:
        A grid centred on the summit (``x = y = 0``).
    """
    rng = np.random.default_rng(seed)
    half = (n - 1) * dx / 2
    x = np.linspace(-half, half, n)
    X, Y = np.meshgrid(x, x)
    R = np.hypot(X, Y)
    az = np.arctan2(X, Y)  # 0 = north, clockwise

    b = height * np.exp(-((R / base_r) ** 1.6))
    b += 120.0 * np.exp(-((R / (2.2 * base_r)) ** 2))  # concave lower apron

    phase = rng.uniform(0, 2 * np.pi)
    wiggle = 0.25 * np.sin(R / 380.0 + phase)
    gully = (0.5 - 0.5 * np.cos(n_gullies * az + wiggle)) ** 3
    gully_depth = 55.0 * np.clip(R / 600.0, 0, 1) * np.exp(-((R / (1.6 * base_r)) ** 2))
    b -= gully_depth * gully

    baz = np.radians(breach_az_deg)
    dang = np.angle(np.exp(1j * (az - baz)))
    b -= 140.0 * np.exp(-((dang / 0.16) ** 2)) * np.exp(-((R / 1900.0) ** 2))

    b -= crater_depth * np.exp(-((R / crater_r) ** 2))
    rim = np.exp(-(((R - 1.15 * crater_r) / 90.0) ** 2))
    b += 35.0 * rim * (1 - 0.9 * np.exp(-((dang / 0.5) ** 2)))

    for k in range(4):
        kx, ky = rng.normal(0, 1, 2) * (k + 1) / 900.0
        b += 6.0 / (k + 1) * np.sin(kx * X + ky * Y + rng.uniform(0, 6.28))
    b += 300.0  # base level a.s.l.
    return Grid(b=b, dx=dx, x0=-half, y0=-half)


def inclined_plane(n: int, dx: float, slope_deg: float) -> Grid:
    """Plane dipping toward −x at ``slope_deg``, centred on the origin."""
    half = (n - 1) * dx / 2
    x = np.linspace(-half, half, n)
    X, _ = np.meshgrid(x, x)
    b = np.tan(np.radians(slope_deg)) * (X - x[0])
    return Grid(b=b, dx=dx, x0=-half, y0=-half)
