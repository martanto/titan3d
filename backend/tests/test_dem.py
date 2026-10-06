"""DEM stitching and domain extraction."""

import os
from pathlib import Path
from collections.abc import Callable

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from titan3d.core.dem import (
    DemError,
    load_domain,
    utm_crs_for,
    lonlat_to_xy,
    preview_grid,
    stitch_tiles,
    inspect_tiles,
)


REPO_DEM = Path(__file__).resolve().parents[2] / "dem"
RES = 0.001  # degrees (~110 m)


def cone(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Analytic test volcano centred at (112.92, -8.11)."""
    r = np.hypot((lon - 112.92) * 110.0, (lat + 8.11) * 110.0)  # km
    return 3600.0 * np.exp(-((r / 4.0) ** 1.5)) + 200.0


def write_tile(
    path: Path, west: float, north: float, n: int, crs: str | None, nodata: float = np.nan
) -> None:
    lon = west + (np.arange(n) + 0.5) * RES
    lat = north - (np.arange(n) + 0.5) * RES
    LON, LAT = np.meshgrid(lon, lat)
    with rasterio.open(
        path, "w", driver="GTiff", height=n, width=n, count=1, dtype="float32",
        crs=crs, transform=from_origin(west, north, RES, RES), nodata=nodata,
    ) as dst:
        dst.write(cone(LON, LAT).astype(np.float32), 1)


@pytest.fixture
def tiles(out_path: Callable[[str], Path]) -> list[Path]:
    """Two side-by-side 100×100 tiles without a CRS (like DEMNAS)."""
    a, b = out_path("dem_tile_a.tif"), out_path("dem_tile_b.tif")
    write_tile(a, 112.82, -8.01, 100, None)
    write_tile(b, 112.92, -8.01, 100, None)
    return [a, b]


def test_inspect_assumes_wgs84_for_lonlat_tiles(tiles: list[Path]) -> None:
    infos = inspect_tiles(tiles)
    assert all(i.crs == "EPSG:4326" and i.crs_assumed for i in infos)


def test_inspect_rejects_projected_bounds_without_crs(out_path) -> None:
    p = out_path("dem_projected_nocrs.tif")
    with rasterio.open(
        p, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
        transform=from_origin(700000, 9100000, 30, 30),
    ) as dst:
        dst.write(np.zeros((4, 4), np.float32), 1)
    with pytest.raises(DemError, match="CRS missing"):
        inspect_tiles([p])


def test_inspect_rejects_non_geotiff(out_path) -> None:
    p = out_path("not_a_dem.tif")
    p.write_text("hello")
    with pytest.raises(DemError, match="not a readable GeoTIFF"):
        inspect_tiles([p])


def test_stitch_two_tiles(tiles: list[Path], out_path) -> None:
    info = stitch_tiles(tiles, out_path("dem_mosaic.tif"))
    assert info.crs == "EPSG:4326"
    assert info.shape == (100, 200)
    np.testing.assert_allclose(info.bounds, (112.82, -8.11, 113.02, -8.01), atol=1e-9)
    assert info.nan_fraction == 0.0
    assert len(info.sha256) == 64
    lon, lat, z = info.summit
    assert abs(lon - 112.92) < 2 * RES and abs(lat + 8.11) < 2 * RES
    assert z > 3500
    with rasterio.open(info.path) as src:
        assert src.crs.to_string() == "EPSG:4326"


def test_stitch_converts_sentinel_nodata(out_path) -> None:
    p = out_path("dem_sentinel.tif")
    write_tile(p, 112.82, -8.01, 50, "EPSG:4326", nodata=-9999.0)
    with rasterio.open(p, "r+") as ds:
        a = ds.read(1)
        a[:5, :5] = -9999.0
        ds.write(a, 1)
    info = stitch_tiles([p], out_path("dem_sentinel_mosaic.tif"))
    assert info.nan_fraction == pytest.approx(25 / 2500)


def test_utm_zone() -> None:
    assert utm_crs_for(112.92, -8.11) == "EPSG:32749"
    assert utm_crs_for(110.44, -7.54) == "EPSG:32749"
    assert utm_crs_for(-122.0, 46.2) == "EPSG:32610"


def test_load_domain_reprojects_to_utm(tiles: list[Path], out_path) -> None:
    info = stitch_tiles(tiles, out_path("dem_mosaic_domain.tif"))
    grid = load_domain(Path(info.path), (112.92, -8.06), (5.0, 5.0, 4.0, 4.0), dx=100.0)
    assert grid.crs == "EPSG:32749"
    assert (grid.ny, grid.nx) == (80, 100)
    assert not np.isnan(grid.b).any()
    # row 0 is the south edge: elevation rises toward the summit at -8.11 (south)
    xs, ys = lonlat_to_xy("EPSG:32749", 112.92, -8.11)
    j, i = grid.index_of(xs, ys)
    assert j == 0 or grid.b[0].max() > grid.b[-1].max()
    assert grid.b.max() > 2000


def test_load_domain_outside_coverage(tiles: list[Path], out_path) -> None:
    info = stitch_tiles(tiles, out_path("dem_mosaic_outside.tif"))
    with pytest.raises(DemError, match="no elevation data"):
        load_domain(Path(info.path), (112.92, -8.06), (5.0, 5.0, 10.0, 4.0), dx=100.0)


def test_preview_grid(tiles: list[Path], out_path) -> None:
    info = stitch_tiles(tiles, out_path("dem_mosaic_preview.tif"))
    grid, valid = preview_grid(Path(info.path), max_cells=64)
    assert max(grid.ny, grid.nx) <= 64
    assert valid.mean() > 0.8


@pytest.mark.skipif(
    not os.environ.get("TITAN3D_REAL_DEM") or not REPO_DEM.exists(),
    reason="set TITAN3D_REAL_DEM=1 to stitch the real Semeru tiles (slow, ~270 MB)",
)
def test_semeru_mosaic_and_default_domain(out_path) -> None:
    info = stitch_tiles(sorted(REPO_DEM.glob("*.tif")), out_path("semeru_mosaic.tif"))
    assert info.shape == (9999, 6666) or info.shape[1] > 6000
    lon, lat, z = info.summit
    assert abs(lon - 112.92) < 0.02 and abs(lat + 8.108) < 0.02 and z > 3500
    grid = load_domain(Path(info.path), (112.922, -8.108), (6.0, 16.0, 14.0, 6.0), 20.0)
    assert (grid.ny, grid.nx) == (1000, 1100)
    assert not np.isnan(grid.b).any()
