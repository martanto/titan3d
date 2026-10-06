"""DEM handling: inspect and stitch GeoTIFF tiles, cut a computational domain.

* Tiles without a CRS are assumed to be EPSG:4326 when their bounds are valid
  longitude/latitude (DEMNAS tiles ship this way); otherwise they are rejected.
* Tiles in different CRSs are warped to the CRS of the first tile.
* Domains are reprojected to the local UTM zone of the vent (square metre cells),
  rows flipped so ``j`` increases northward.
"""

import math
import hashlib
from typing import Any
from pathlib import Path
from dataclasses import asdict, dataclass
from collections.abc import Sequence

import numpy as np
import rasterio
from rasterio import CRS
from rasterio.vrt import WarpedVRT
from rasterio.fill import fillnodata
from rasterio.warp import transform as warp_transform, transform_bounds
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_origin

from titan3d.core.grid import Grid


ASSUMED_CRS = "EPSG:4326"
MAX_NAN_FRACTION = 0.005
"""Largest fraction of nodata cells a domain may contain before it is rejected."""


class DemError(ValueError):
    """Raised for unusable DEM input or domains outside DEM coverage."""


@dataclass(frozen=True)
class TileInfo:
    """Metadata of one input tile.

    Attributes:
        path: File path.
        crs: CRS authority string used for the tile.
        crs_assumed: Whether the CRS was missing and assumed to be EPSG:4326.
        bounds: ``(west, south, east, north)`` in the tile CRS.
        res: Pixel size ``(x, y)`` in CRS units.
        shape: ``(rows, cols)``.
        dtype: Band data type.
        nodata: Declared nodata value.
    """

    path: str
    crs: str
    crs_assumed: bool
    bounds: tuple[float, float, float, float]
    res: tuple[float, float]
    shape: tuple[int, int]
    dtype: str
    nodata: float | None


@dataclass(frozen=True)
class MosaicInfo:
    """Metadata of a stitched mosaic.

    Attributes:
        path: Mosaic GeoTIFF path.
        crs: CRS authority string.
        bounds: ``(west, south, east, north)`` in the mosaic CRS.
        bounds_lonlat: Bounds in EPSG:4326.
        res: Pixel size ``(x, y)`` in CRS units.
        res_m: Approximate pixel size in metres.
        shape: ``(rows, cols)``.
        nan_fraction: Fraction of nodata pixels.
        summit: ``(lon, lat, elevation)`` of the highest pixel.
        zmin: Lowest valid elevation [m].
        sha256: Hash of the mosaic file.
        tiles: Number of input tiles.
        crs_assumed: Whether any tile's CRS was assumed.
    """

    path: str
    crs: str
    bounds: tuple[float, float, float, float]
    bounds_lonlat: tuple[float, float, float, float]
    res: tuple[float, float]
    res_m: float
    shape: tuple[int, int]
    nan_fraction: float
    summit: tuple[float, float, float]
    zmin: float
    sha256: str
    tiles: int
    crs_assumed: bool

    def to_dict(self) -> dict[str, Any]:
        """Plain dict for JSON."""
        return asdict(self)


def _looks_geographic(b: tuple[float, float, float, float]) -> bool:
    w, s, e, n = b
    return -180.0 <= w < e <= 180.0 and -90.0 <= s < n <= 90.0


def inspect_tiles(paths: Sequence[Path]) -> list[TileInfo]:
    """Validate tiles and resolve their CRS.

    Args:
        paths: GeoTIFF files.

    Returns:
        One :class:`TileInfo` per file.

    Raises:
        DemError: If a file is unreadable, multi-band, non-numeric, or has no CRS
            and non-geographic bounds.
    """
    if not paths:
        raise DemError("No DEM files given.")
    infos = []
    for p in paths:
        try:
            with rasterio.open(p) as src:
                if src.count < 1:
                    raise DemError(f"{Path(p).name}: no raster bands.")
                dtype = src.dtypes[0]
                if not np.issubdtype(np.dtype(dtype), np.number):
                    raise DemError(f"{Path(p).name}: band type {dtype} is not numeric.")
                sb = src.bounds
                b = (float(sb.left), float(sb.bottom), float(sb.right), float(sb.top))
                assumed = src.crs is None
                if assumed and not _looks_geographic(b):
                    raise DemError(
                        f"{Path(p).name}: CRS missing and bounds {b} are not "
                        "longitude/latitude; add a CRS to the file."
                    )
                crs = ASSUMED_CRS if assumed else src.crs.to_string()
                infos.append(
                    TileInfo(
                        path=str(p),
                        crs=crs,
                        crs_assumed=assumed,
                        bounds=b,
                        res=(float(src.res[0]), float(src.res[1])),
                        shape=(src.height, src.width),
                        dtype=dtype,
                        nodata=None if src.nodata is None else float(src.nodata),
                    )
                )
        except rasterio.errors.RasterioIOError as exc:
            raise DemError(f"{Path(p).name}: not a readable GeoTIFF ({exc}).") from exc
    return infos


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _approx_res_m(crs: CRS, res: tuple[float, float], lat: float) -> float:
    if crs.is_geographic:
        return float(res[0] * 111_320.0 * math.cos(math.radians(lat)))
    return float(res[0])


def stitch_tiles(paths: Sequence[Path], out_path: Path) -> MosaicInfo:
    """Merge tiles into one float32 GeoTIFF with NaN nodata.

    Args:
        paths: Input GeoTIFF tiles.
        out_path: Output mosaic path (deflate-compressed, tiled).

    Returns:
        Mosaic metadata, including the highest point and a file hash.
    """
    infos = inspect_tiles(paths)
    target = CRS.from_string(infos[0].crs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    srcs = [rasterio.open(i.path) for i in infos]
    try:
        datasets: list[Any] = []
        for info, src in zip(infos, srcs, strict=True):
            if CRS.from_string(info.crs) == target:
                datasets.append(src)  # same CRS (or both assumed): merge directly
                continue
            datasets.append(
                WarpedVRT(
                    src,
                    src_crs=CRS.from_string(info.crs),
                    crs=target,
                    resampling=Resampling.bilinear,
                    src_nodata=info.nodata,
                    nodata=np.nan,
                    dtype="float32",
                )
            )
        arr, transform = merge(
            datasets, nodata=np.nan, dtype="float32", resampling=Resampling.bilinear
        )
        for d in datasets:
            if isinstance(d, WarpedVRT):
                d.close()
    finally:
        for s in srcs:
            s.close()

    band = arr[0].astype(np.float32)
    for info in infos:  # declared nodata that merge left as values (e.g. -9999)
        if info.nodata is not None and not math.isnan(info.nodata):
            band[band == info.nodata] = np.nan
    band[band < -1000.0] = np.nan  # sentinel nodata (−9999, −32767) left undeclared
    rows, cols = band.shape
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=target,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
        predictor=3,
        tiled=True,
        blockxsize=512,
        blockysize=512,
        BIGTIFF="IF_SAFER",
    ) as dst:
        dst.write(band, 1)

    valid = ~np.isnan(band)
    if not valid.any():
        raise DemError("The stitched DEM contains no valid elevations.")
    k = int(np.nanargmax(band))
    r, c = divmod(k, cols)
    sx, sy = rasterio.transform.xy(transform, r, c)
    bounds = rasterio.transform.array_bounds(rows, cols, transform)
    w, s, e, n = bounds[0], bounds[1], bounds[2], bounds[3]
    bounds_ll = transform_bounds(target, ASSUMED_CRS, w, s, e, n)
    lon, lat = warp_transform(target, ASSUMED_CRS, [sx], [sy])
    res = (abs(transform.a), abs(transform.e))
    return MosaicInfo(
        path=str(out_path),
        crs=target.to_string(),
        bounds=(w, s, e, n),
        bounds_lonlat=(
            float(bounds_ll[0]),
            float(bounds_ll[1]),
            float(bounds_ll[2]),
            float(bounds_ll[3]),
        ),
        res=res,
        res_m=_approx_res_m(target, res, (bounds_ll[1] + bounds_ll[3]) / 2),
        shape=(rows, cols),
        nan_fraction=float(1.0 - valid.mean()),
        summit=(float(lon[0]), float(lat[0]), float(band[r, c])),
        zmin=float(np.nanmin(band)),
        sha256=_sha256(out_path),
        tiles=len(infos),
        crs_assumed=any(i.crs_assumed for i in infos),
    )


def utm_crs_for(lon: float, lat: float) -> str:
    """EPSG code of the UTM zone containing a point (e.g. ``EPSG:32749``)."""
    zone = int((lon + 180.0) // 6.0) % 60 + 1
    return f"EPSG:{(32700 if lat < 0 else 32600) + zone}"


def lonlat_to_xy(crs: str, lon: float, lat: float) -> tuple[float, float]:
    """Project a longitude/latitude to ``crs``."""
    xs, ys = warp_transform(ASSUMED_CRS, crs, [lon], [lat])
    return float(xs[0]), float(ys[0])


def xy_to_lonlat(crs: str, x: float, y: float) -> tuple[float, float]:
    """Unproject a point in ``crs`` to longitude/latitude."""
    lons, lats = warp_transform(crs, ASSUMED_CRS, [x], [y])
    return float(lons[0]), float(lats[0])


def _mosaic_crs(src: rasterio.DatasetReader) -> CRS:
    return src.crs if src.crs is not None else CRS.from_string(ASSUMED_CRS)


def _warp(
    mosaic: Path, dst_crs: str, west: float, north: float, dx: float, nx: int, ny: int
) -> np.ndarray:
    with rasterio.open(mosaic) as src:
        with WarpedVRT(
            src,
            src_crs=_mosaic_crs(src),
            crs=dst_crs,
            transform=from_origin(west, north, dx, dx),
            width=nx,
            height=ny,
            resampling=Resampling.bilinear,
            src_nodata=np.nan if src.nodata is None else src.nodata,
            nodata=np.nan,
            dtype="float32",
        ) as vrt:
            return vrt.read(1)


def load_domain(
    mosaic: Path,
    center_lonlat: tuple[float, float],
    extents_km: tuple[float, float, float, float],
    dx: float,
    max_nan_fraction: float = MAX_NAN_FRACTION,
) -> Grid:
    """Cut and reproject a computational domain from a mosaic.

    Args:
        mosaic: Stitched DEM.
        center_lonlat: Domain anchor (usually the vent) ``(lon, lat)``.
        extents_km: Distances from the anchor ``(west, east, south, north)`` [km].
        dx: Cell size [m].
        max_nan_fraction: Reject domains with more nodata than this.

    Returns:
        A north-up :class:`Grid` in the local UTM zone.

    Raises:
        DemError: If the domain leaves the DEM coverage.
    """
    if dx <= 0:
        raise DemError("Cell size must be positive.")
    lon, lat = center_lonlat
    crs = utm_crs_for(lon, lat)
    xc, yc = lonlat_to_xy(crs, lon, lat)
    w_km, e_km, s_km, n_km = extents_km
    nx = max(int(round((w_km + e_km) * 1000.0 / dx)), 8)
    ny = max(int(round((s_km + n_km) * 1000.0 / dx)), 8)
    west = round((xc - w_km * 1000.0) / dx) * dx
    south = round((yc - s_km * 1000.0) / dx) * dx
    north = south + ny * dx
    arr = _warp(mosaic, crs, west, north, dx, nx, ny)
    nan = np.isnan(arr)
    frac = float(nan.mean())
    if frac > max_nan_fraction:
        rows, cols = np.nonzero(nan)
        where = []
        if cols.min() < nx * 0.1:
            where.append("west")
        if cols.max() > nx * 0.9:
            where.append("east")
        if rows.min() < ny * 0.1:
            where.append("north")
        if rows.max() > ny * 0.9:
            where.append("south")
        side = ", ".join(where) or "interior"
        raise DemError(
            f"{frac:.1%} of the domain has no elevation data ({side} side). "
            "Shrink the extents or use a DEM that covers the area."
        )
    if frac > 0:
        arr = fillnodata(arr, mask=(~nan).astype(np.uint8), max_search_distance=50)
        arr = np.where(np.isnan(arr), np.nanmin(arr), arr)
    return Grid(
        b=np.ascontiguousarray(arr[::-1].astype(np.float64)),
        dx=float(dx),
        x0=west + dx / 2,
        y0=south + dx / 2,
        crs=crs,
    )


def preview_grid(mosaic: Path, max_cells: int = 512) -> tuple[Grid, np.ndarray]:
    """Whole-mosaic grid in the UTM zone of its centre, for terrain previews.

    Returns:
        ``(grid, valid)`` where ``valid`` marks cells with data (row order as grid).
    """
    with rasterio.open(mosaic) as src:
        bll = transform_bounds(_mosaic_crs(src), ASSUMED_CRS, *src.bounds)
    lon, lat = (bll[0] + bll[2]) / 2, (bll[1] + bll[3]) / 2
    crs = utm_crs_for(lon, lat)
    w, s, e, n = transform_bounds(ASSUMED_CRS, crs, *bll)
    dx = max(e - w, n - s) / max_cells
    nx, ny = max(int((e - w) / dx), 2), max(int((n - s) / dx), 2)
    arr = _warp(mosaic, crs, w, n, dx, nx, ny)[::-1]
    valid = ~np.isnan(arr)
    return Grid(
        b=arr.astype(np.float64), dx=dx, x0=w + dx / 2, y0=s + dx / 2, crs=crs
    ), valid
