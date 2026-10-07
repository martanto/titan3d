"""Synthetic checks of comparison accounting; no Titan2D dependency required."""

import numpy as np
import pytest

from titan3d.core.grid import Grid
from tests.colima_comparison import (
    CENTER,
    ANALYTIC_VOLUME,
    depth_metrics,
    cylinder_depth,
    rasterize_cells,
    read_adaptive_state,
)


def test_conservative_adaptive_rasterization() -> None:
    grid = Grid(np.zeros((2, 2)), 1, 0.5, 0.5)
    cells = np.array([[0, 0, 0.5, 2], [0.5, 0, 2, 2]])
    h = np.array([2, 4])
    raster = rasterize_cells(cells, h, grid)
    np.testing.assert_allclose(raster, [[3, 4], [3, 4]])
    assert raster.sum() == pytest.approx(
        np.sum(h * (cells[:, 2] - cells[:, 0]) * (cells[:, 3] - cells[:, 1]))
    )


def test_depth_metrics_include_wet_union() -> None:
    metrics = depth_metrics(np.array([[2, 0.0]]), np.array([[0, 2.0]]), 5)
    assert metrics["footprint_iou"] == 0
    assert metrics["mae_m"] == 2
    assert metrics["bias_m"] == 0
    assert metrics["reference_area_m2"] == 25
    assert depth_metrics(np.zeros((1, 1)), np.zeros((1, 1)), 5)["footprint_iou"] == 1


@pytest.mark.parametrize("dx", [2.5, 5, 10])
def test_cylinder_quadrature_volume(dx: float) -> None:
    grid = Grid(
        np.zeros((int(200 / dx), int(200 / dx))),
        dx,
        CENTER[0] - 100 + dx / 2,
        CENTER[1] - 100 + dx / 2,
    )
    h = cylinder_depth(grid)
    assert h.min() >= 0 and h.max() == 30
    assert h.sum() * dx**2 == pytest.approx(ANALYTIC_VOLUME, rel=2e-4)


def test_rasterization_clips_domain_and_handles_dry_cells() -> None:
    grid = Grid(np.zeros((1, 1)), 1, 0.5, 0.5)
    cells = np.array([[-1, -1, 0.5, 0.5], [0.5, 0, 1, 1], [4, 4, 5, 5]])
    np.testing.assert_allclose(rasterize_cells(cells, np.array([4, 2, 8]), grid), [[2]])
    np.testing.assert_array_equal(rasterize_cells(cells, np.zeros(3), grid), [[0]])


@pytest.mark.parametrize("value", [np.nan, np.inf, -1])
def test_metrics_reject_invalid_depth(value: float) -> None:
    with pytest.raises(ValueError):
        depth_metrics(np.array([[value]]), np.zeros((1, 1)), 5)


def test_xdmf_field_extraction(out_path) -> None:
    import xml.etree.ElementTree as ET

    h5py = pytest.importorskip("h5py")
    path = out_path("colima-state.h5")
    with h5py.File(path, "w") as hdf:
        hdf["points"] = np.array([[0, 0, 10], [2, 0, 20], [2, 3, 30], [0, 3, 40]])
        hdf["connections"] = [[0, 1, 2, 3]]
        hdf["depth"] = [[2.0]]
        hdf["hu"] = [[6.0]]
        hdf["hv"] = [[8.0]]

    def item(dataset):
        return f'<DataItem Format="HDF">{path.name}:/{dataset}</DataItem>'

    xml = ET.fromstring(
        f'<Grid><Geometry>{item("points")}</Geometry><Topology>{item("connections")}</Topology><Attribute Name="Pile Height">{item("depth")}</Attribute><Attribute Name="X_Momentum">{item("hu")}</Attribute><Attribute Name="Y_Momentum">{item("hv")}</Attribute></Grid>'
    )
    bounds, area, h, hu, hv = read_adaptive_state(xml, path.parent)
    np.testing.assert_array_equal(bounds, [[0, 0, 2, 3]])
    assert (h * area).sum() == 12  # projected area, not sloped surface area
    assert np.hypot(hu, hv)[0] / h[0] == 5
