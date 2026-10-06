"""Verification cases for the finite-volume solver (NumPy backend)."""

import numpy as np
import pytest

from titan3d.core.grid import Grid
from titan3d.core.params import Backend, FlowParams, EarthPressure
from titan3d.core.solver import Solver
from titan3d.core.sources import paraboloid
from titan3d.core.terrain import inclined_plane, synthetic_volcano


def numpy_params(**kw: object) -> FlowParams:
    base: dict[str, object] = {"backend": Backend.NUMPY}
    base.update(kw)
    return FlowParams(**base)  # type: ignore[arg-type]


def test_lake_at_rest_over_bump() -> None:
    n, dx = 64, 20.0
    x = (np.arange(n) - n / 2) * dx
    X, Y = np.meshgrid(x, x)
    b = 30.0 * np.exp(-(X**2 + Y**2) / 200.0**2)
    grid = Grid(b=b, dx=dx, x0=x[0], y0=x[0])
    solver = Solver(grid, numpy_params(phi_bed_deg=0.0, curvature=False,
                                       earth_pressure=EarthPressure.HYDROSTATIC))
    s = solver.initial_state(50.0 - b)
    for _ in range(50):
        s = solver.step(s, solver.max_dt(s))
    assert np.abs(s.hu).max() < 1e-10
    assert np.abs(s.hv).max() < 1e-10
    assert np.abs(s.h + b - 50.0).max() < 1e-10


def test_pile_stays_on_slope_flatter_than_friction() -> None:
    grid = inclined_plane(n=64, dx=10.0, slope_deg=10.0)
    solver = Solver(grid, numpy_params(phi_bed_deg=20.0, phi_int_deg=30.0))
    h0 = paraboloid(grid.x, grid.y, 0.0, 0.0, 5.0, 100.0)
    s = solver.initial_state(h0)
    for st in solver.run(s, t_end=20.0, output_every=20.0):
        s = st
    X, _ = np.meshgrid(grid.x, grid.y)
    shift = (s.h * X).sum() / s.h.sum() - (h0 * X).sum() / h0.sum()
    speed = np.hypot(s.hu, s.hv) / np.maximum(s.h, 1e-3)
    assert abs(shift) < 1.0
    assert speed.max() < 0.5


def test_symmetric_pile_stays_symmetric() -> None:
    grid = inclined_plane(n=81, dx=10.0, slope_deg=30.0)
    solver = Solver(grid, numpy_params(phi_bed_deg=20.0))
    s = solver.initial_state(paraboloid(grid.x, grid.y, 100.0, 0.0, 10.0, 80.0))
    for st in solver.run(s, t_end=15.0, output_every=15.0):
        s = st
    assert s.h.max() > 0
    np.testing.assert_allclose(s.h, s.h[::-1, :], atol=1e-10)
    np.testing.assert_allclose(s.hu, s.hu[::-1, :], atol=1e-10)
    np.testing.assert_allclose(s.hv, -s.hv[::-1, :], atol=1e-10)


def test_mass_balance_with_outflow() -> None:
    grid = synthetic_volcano(n=80, dx=60.0, base_r=1500.0)
    solver = Solver(grid, numpy_params(phi_bed_deg=14.0))
    h0 = paraboloid(grid.x, grid.y, 0.0, -100.0, 60.0, 300.0)
    v0 = solver.volume(h0)
    s = solver.initial_state(h0)
    for st in solver.run(s, t_end=120.0, output_every=30.0):
        s = st
    assert s.vol_out > 0.01 * v0, "test should exercise outflow"
    assert abs(solver.volume(s.h) + s.vol_out - v0) / v0 < 1e-5


class FullDomainSolver(Solver):
    """Solver that always computes on the whole grid."""

    def step_window(self, s):  # type: ignore[override]
        if not s.h.any():
            return None
        return slice(0, self.ny), slice(0, self.nx)


@pytest.mark.parametrize("pressure", list(EarthPressure))
def test_active_window_matches_full_domain(pressure: EarthPressure) -> None:
    grid = synthetic_volcano(n=96, dx=50.0, base_r=1500.0)
    params = numpy_params(phi_bed_deg=20.0, earth_pressure=pressure)
    h0 = paraboloid(grid.x, grid.y, 0.0, -100.0, 50.0, 250.0)
    a, b = Solver(grid, params), FullDomainSolver(grid, params)
    sa, sb = a.initial_state(h0), b.initial_state(h0)
    for _ in range(60):
        dt = a.max_dt(sa)
        sa, sb = a.step(sa, dt), b.step(sb, dt)
    assert sa.box is not None and sa.box != (0, a.ny, 0, a.nx)
    assert sa.box == a.kernels.wet_box(sa.h, 0, 0)
    np.testing.assert_array_equal(sa.h, sb.h)
    np.testing.assert_array_equal(sa.hu, sb.hu)
    np.testing.assert_array_equal(sa.hv, sb.hv)


def test_dry_domain_skips_to_output() -> None:
    grid = inclined_plane(n=16, dx=10.0, slope_deg=5.0)
    solver = Solver(grid, numpy_params())
    s = solver.initial_state(np.zeros_like(grid.b))
    frames = list(solver.run(s, t_end=10.0, output_every=5.0))
    assert [f.t for f in frames] == [0.0, 5.0, 10.0]
