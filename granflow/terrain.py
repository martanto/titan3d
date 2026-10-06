"""Terrain and initial-condition helpers (Titan2D-style piles)."""
from __future__ import annotations

import numpy as np


def synthetic_volcano(n: int = 256, dx: float = 25.0, height: float = 1700.0,
                      base_r: float = 2600.0, crater_r: float = 260.0,
                      breach_az_deg: float = 200.0, n_gullies: int = 9,
                      crater_depth: float = 120.0,
                      seed: int = 7):
    """Stratovolcano with a summit crater breached toward `breach_az_deg`
    (degrees clockwise from north) and radial erosional gullies.

    Returns (x, y, b) with x, y 1-D coordinates centred on the summit.
    """
    rng = np.random.default_rng(seed)
    half = (n - 1) * dx / 2
    x = np.linspace(-half, half, n)
    y = np.linspace(-half, half, n)
    X, Y = np.meshgrid(x, y)
    R = np.hypot(X, Y)
    az = np.arctan2(X, Y)                       # 0 = north, clockwise

    cone = height * np.exp(-(R / base_r) ** 1.6)
    # concave lower apron
    cone += 120.0 * np.exp(-(R / (2.2 * base_r)) ** 2)

    # radial gullies, deepening downslope then fading on the apron
    phase = rng.uniform(0, 2 * np.pi)
    wiggle = 0.25 * np.sin(R / 380.0 + phase)
    gully = (0.5 - 0.5 * np.cos(n_gullies * az + wiggle)) ** 3
    gully_depth = 55.0 * np.clip(R / 600.0, 0, 1) * np.exp(-(R / (1.6 * base_r)) ** 2)
    b = cone - gully_depth * gully

    # breach valley from the crater, steering material one way
    baz = np.radians(breach_az_deg)
    dang = np.angle(np.exp(1j * (az - baz)))
    valley = np.exp(-(dang / 0.16) ** 2) * np.exp(-(R / 1900.0) ** 2)
    b -= 140.0 * valley

    # summit crater (rim + bowl)
    b -= crater_depth * np.exp(-(R / crater_r) ** 2)
    b += 35.0 * np.exp(-((R - 1.15 * crater_r) / 90.0) ** 2) * (1 - 0.9 * np.exp(-(dang / 0.5) ** 2))

    # low-amplitude roughness
    for k in range(4):
        kx, ky = rng.normal(0, 1, 2) * (k + 1) / 900.0
        b += 6.0 / (k + 1) * np.sin(kx * X + ky * Y + rng.uniform(0, 6.28))
    b += 300.0                                     # base level a.s.l.
    return x, y, b


def paraboloid_pile(x, y, xc, yc, height, radius):
    """Titan2D's default pile: h = H (1 - r^2 / R^2), clipped at 0."""
    X, Y = np.meshgrid(x, y)
    r2 = ((X - xc) ** 2 + (Y - yc) ** 2) / radius ** 2
    return np.clip(height * (1.0 - r2), 0.0, None)


def load_dem(path: str):
    """Load a GeoTIFF (requires rasterio) or .npy DEM. Returns (b, dx)."""
    if path.endswith(".npy"):
        return np.load(path), None
    import rasterio  # optional dependency
    with rasterio.open(path) as src:
        b = src.read(1).astype(np.float64)[::-1]   # south-up for array y
        dx = abs(src.transform.a)
    return b, dx
