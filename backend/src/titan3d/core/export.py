"""Run outputs: viewer bundle, GeoTIFF maxima, inundation outline (GeoJSON / KML).

Viewer bundle fields are quantised, zlib-compressed and base64 encoded:

* ``terrain``    uint16  ``(b - zmin) / (zmax - zmin)``
* ``depth``      uint8   ``sqrt(h / hmax)`` per frame (sqrt keeps thin margins visible)
* ``speed``      uint8   ``|u| / vmax`` per frame
* ``hmaxField``  uint8   ``sqrt(h_max / hmax)`` over every step

Large grids are reduced for the browser: terrain by block mean, depth and speed
by block maximum (so thin fronts are not lost).
"""

import json
import zlib
import base64
from typing import Any
from pathlib import Path
from collections.abc import Callable
from xml.sax.saxutils import escape

import numpy as np

from titan3d.core.grid import Grid
from titan3d.core.stats import FrameStats
from titan3d.core.params import FloatArray


FrameLoader = Callable[[int], tuple[FloatArray, FloatArray]]


def _pack(arr: np.ndarray) -> str:
    return base64.b64encode(
        zlib.compress(np.ascontiguousarray(arr).tobytes(), 6)
    ).decode()


def display_stride(ny: int, nx: int, max_cells: int) -> int:
    """Integer reduction factor so neither side exceeds ``max_cells``."""
    return max(1, int(np.ceil(max(ny, nx) / max_cells)))


def reduce_block(a: FloatArray, s: int, how: str) -> FloatArray:
    """Reduce a 2-D array by ``s × s`` blocks (``"mean"`` or ``"max"``)."""
    if s == 1:
        return a
    ny, nx = a.shape
    py, px = (-ny) % s, (-nx) % s
    a = np.pad(a, ((0, py), (0, px)), mode="edge")
    blocks = a.reshape(a.shape[0] // s, s, a.shape[1] // s, s)
    return blocks.mean(axis=(1, 3)) if how == "mean" else blocks.max(axis=(1, 3))


def _quantise(a: FloatArray, scale: float, sqrt: bool) -> np.ndarray:
    v = np.clip(a / scale, 0.0, 1.0)
    if sqrt:
        v = np.sqrt(v)
    return np.round(v * 255).astype(np.uint8)


def viewer_bundle(
    grid: Grid,
    load_frame: FrameLoader,
    stats: list[FrameStats],
    h_max: FloatArray,
    meta: dict[str, Any],
    max_cells: int = 640,
) -> dict[str, Any]:
    """Build the compact JSON bundle the frontend plays back.

    Args:
        grid: Computational grid.
        load_frame: Returns ``(h, speed)`` for frame ``k``.
        stats: Per-frame statistics (also gives the global maxima).
        h_max: Per-cell maximum depth over every step.
        meta: Extra metadata merged into ``bundle["meta"]``.
        max_cells: Maximum cells per side in the bundle.

    Returns:
        A JSON-serialisable dict.
    """
    s = display_stride(grid.ny, grid.nx, max_cells)
    b = reduce_block(grid.b.astype(np.float64), s, "mean")
    zmin, zmax = float(np.min(b)), float(np.max(b))
    hmax = max(float(np.max(h_max)), 1e-3)
    n = len(stats)
    # pass 1: global speed maximum; pass 2: quantise (keeps memory at uint8 size)
    vmax = max([1e-3] + [float(np.max(load_frame(k)[1])) for k in range(n)])
    depth, speed = [], []
    for k in range(n):
        h, u = load_frame(k)
        depth.append(_quantise(reduce_block(h, s, "max"), hmax, sqrt=True))
        speed.append(_quantise(reduce_block(u, s, "max"), vmax, sqrt=False))
    terr = np.round((b - zmin) / max(zmax - zmin, 1e-9) * 65535).astype("<u2")
    ny, nx = b.shape
    return {
        "meta": {
            **meta,
            "nx": nx,
            "ny": ny,
            "dx": grid.dx * s,
            "stride": s,
            "x0": grid.x0 + (s - 1) * grid.dx / 2,
            "y0": grid.y0 + (s - 1) * grid.dx / 2,
            "crs": grid.crs,
            "nframes": n,
            "zmin": zmin,
            "zmax": zmax,
            "hmax": hmax,
            "vmax": vmax,
        },
        "stats": [st.to_dict() for st in stats],
        "terrain": _pack(terr),
        "depth": _pack(np.stack(depth)),
        "speed": _pack(np.stack(speed)),
        "hmaxField": _pack(_quantise(reduce_block(h_max, s, "max"), hmax, sqrt=True)),
    }


def terrain_preview(
    grid: Grid, meta: dict[str, Any], max_cells: int = 512
) -> dict[str, Any]:
    """Terrain-only bundle (same encoding as :func:`viewer_bundle`)."""
    s = display_stride(grid.ny, grid.nx, max_cells)
    b = reduce_block(grid.b.astype(np.float64), s, "mean")
    zmin, zmax = float(np.nanmin(b)), float(np.nanmax(b))
    b = np.nan_to_num(b, nan=zmin)
    terr = np.round((b - zmin) / max(zmax - zmin, 1e-9) * 65535).astype("<u2")
    ny, nx = b.shape
    return {
        "meta": {
            **meta,
            "nx": nx,
            "ny": ny,
            "dx": grid.dx * s,
            "x0": grid.x0 + (s - 1) * grid.dx / 2,
            "y0": grid.y0 + (s - 1) * grid.dx / 2,
            "crs": grid.crs,
            "zmin": zmin,
            "zmax": zmax,
        },
        "terrain": _pack(terr),
    }


def write_json_gz(path: Path, data: dict[str, Any]) -> None:
    """Write compact JSON, gzip-compressed."""
    import gzip

    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(data, f, separators=(",", ":"))


def write_geotiff(path: Path, arr: FloatArray, grid: Grid) -> None:
    """Write a single-band float32 GeoTIFF in the grid's CRS (north-up)."""
    import rasterio
    from rasterio.transform import from_origin

    w, _, _, n = grid.bounds
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=grid.ny,
        width=grid.nx,
        count=1,
        dtype="float32",
        crs=grid.crs,
        transform=from_origin(w, n, grid.dx, grid.dx),
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(np.ascontiguousarray(arr[::-1].astype(np.float32)), 1)


def inundation_geojson(
    grid: Grid, h_max: FloatArray, threshold: float = 0.1
) -> dict[str, Any]:
    """Outline of cells whose maximum depth exceeded ``threshold``.

    Polygons follow cell edges (holes kept) and are reprojected to EPSG:4326
    when the grid has a CRS; otherwise they stay in grid coordinates.
    """
    from rasterio.warp import transform_geom
    from rasterio.features import shapes
    from rasterio.transform import from_origin

    mask = h_max[::-1] > threshold
    w, _, _, n = grid.bounds
    tr = from_origin(w, n, grid.dx, grid.dx)
    features = []
    for geom, _ in shapes(mask.astype(np.uint8), mask=mask, transform=tr):
        if grid.crs:
            geom = transform_geom(grid.crs, "EPSG:4326", geom, precision=7)
        features.append({"type": "Feature", "geometry": geom, "properties": {}})
    area_km2 = float(mask.sum()) * grid.dx**2 / 1e6
    return {
        "type": "FeatureCollection",
        "name": "inundation",
        "crs_note": "EPSG:4326" if grid.crs else "grid coordinates (no CRS)",
        "properties": {"threshold_m": threshold, "area_km2": round(area_km2, 4)},
        "features": features,
    }


def geojson_to_kml(fc: dict[str, Any], name: str = "titan3d inundation") -> str:
    """Convert an inundation FeatureCollection (EPSG:4326) to KML."""

    def ring(coords: list[list[float]]) -> str:
        return " ".join(f"{c[0]:.7f},{c[1]:.7f},0" for c in coords)

    marks = []
    for k, f in enumerate(fc["features"]):
        rings = f["geometry"]["coordinates"]
        inner = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{ring(r)}</coordinates>"
            "</LinearRing></innerBoundaryIs>"
            for r in rings[1:]
        )
        marks.append(
            f"<Placemark><name>area {k + 1}</name><styleUrl>#inund</styleUrl><Polygon>"
            f"<outerBoundaryIs><LinearRing><coordinates>{ring(rings[0])}</coordinates>"
            f"</LinearRing></outerBoundaryIs>{inner}</Polygon></Placemark>"
        )
    thr = fc.get("properties", {}).get("threshold_m", "")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{escape(name)}</name>"
        f"<description>Maximum flow depth above {thr} m</description>"
        '<Style id="inund"><LineStyle><color>ff1e3ab2</color><width>2</width></LineStyle>'
        "<PolyStyle><color>661e3ab2</color></PolyStyle></Style>"
        + "".join(marks)
        + "</Document></kml>\n"
    )
