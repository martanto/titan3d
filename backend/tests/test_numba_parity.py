"""Numba kernels reproduce the NumPy reference; float32 stays within tolerance."""

import numpy as np
import pytest

from titan3d.core.params import Backend, Precision, FlowParams, EarthPressure
from titan3d.core.solver import Solver
from titan3d.core.sources import paraboloid
from titan3d.core.terrain import synthetic_volcano


GRID = synthetic_volcano(n=96, dx=50.0, base_r=1500.0)
H0 = paraboloid(GRID.x, GRID.y, 0.0, -100.0, 50.0, 250.0)


def advance(params: FlowParams, steps: int = 60, dts: list[float] | None = None):
    solver = Solver(GRID, params)
    s = solver.initial_state(H0)
    used = []
    for k in range(steps):
        dt = dts[k] if dts else solver.max_dt(s)
        used.append(dt)
        s = solver.step(s, dt)
    return solver, s, used


@pytest.mark.parametrize("pressure", list(EarthPressure))
@pytest.mark.parametrize("curvature", [False, True])
def test_numba_matches_numpy(pressure: EarthPressure, curvature: bool) -> None:
    kw = {"phi_bed_deg": 20.0, "earth_pressure": pressure, "curvature": curvature}
    ref_solver, ref, dts = advance(FlowParams(backend=Backend.NUMPY, **kw))
    nb_solver, nb, _ = advance(FlowParams(backend=Backend.NUMBA, **kw), dts=dts)
    assert nb_solver.backend == Backend.NUMBA
    scale = float(np.abs(ref.hu).max())
    np.testing.assert_allclose(nb.h, ref.h, rtol=0, atol=1e-10)
    np.testing.assert_allclose(nb.hu, ref.hu, rtol=0, atol=1e-10 * scale)
    np.testing.assert_allclose(nb.hv, ref.hv, rtol=0, atol=1e-10 * scale)


def test_float32_conserves_mass_and_matches_runout() -> None:
    kw = {"phi_bed_deg": 20.0, "backend": Backend.NUMBA}
    s64_solver, s64, dts = advance(FlowParams(precision=Precision.FLOAT64, **kw), 120)
    s32_solver, s32, _ = advance(FlowParams(precision=Precision.FLOAT32, **kw), 120, dts)
    assert s32.h.dtype == np.float32
    v0 = s64_solver.volume(H0)
    assert abs(s32_solver.volume(s32.h) + s32.vol_out - v0) / v0 < 1e-5
    w64 = s64.h > 0.1
    w32 = s32.h > 0.1
    # footprints agree except along the margin (within one cell)
    assert (w64 ^ w32).sum() < 0.02 * w64.sum()
