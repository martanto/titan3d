"""Independent conservation, equilibrium and mixed-interface AMR checks."""

import numpy as np
import pytest

from titan3d.core.amr import AdaptiveSolver
from titan3d.core.grid import Grid
from titan3d.core.params import (
    Backend,
    Rheology,
    Precision,
    FlowParams,
    FluxSource,
    EarthPressure,
)
from titan3d.core.solver import Solver
from titan3d.core.sources import paraboloid
from titan3d.core.amr_mesh import LeafMesh, waterfill


def params(**kwargs):
    return FlowParams(
        backend=Backend.NUMPY,
        earth_pressure=EarthPressure.HYDROSTATIC,
        phi_bed_deg=0,
        curvature=False,
        **kwargs,
    )


def grid(n=32):
    return Grid(np.zeros((n, n)), 1, x0=0.5, y0=0.5, crs="EPSG:32613")


def mixed(g):
    mask = np.zeros(((g.ny + 1) // 2, (g.nx + 1) // 2), dtype=bool)
    mask[:, mask.shape[1] // 2 :] = True
    return mask


def test_waterfill_wet_dry_and_momentum_transfer():
    beds = np.array([[0, 1, 3, 8], [2, 2, 2, 2], [0, 1, 2, 3]], dtype=float)
    depths = np.array([0.1, 0, 10])
    split = waterfill(depths, beds)
    np.testing.assert_allclose(split.mean(axis=1), depths, atol=1e-14)
    assert (split >= 0).all()
    np.testing.assert_allclose(split[0], [0.4, 0, 0, 0], atol=1e-14)
    np.testing.assert_allclose(split[2] + beds[2], 11.5)
    g = grid()
    g.b[:] = np.arange(g.nx)[None, :] * 0.1
    m = LeafMesh(g, mixed(g))
    h = np.full(m.n, 2.0)
    rasters = m.raster(h, 3 * h, -2 * h)
    for field, expected in zip(rasters, (h, 3 * h, -2 * h), strict=True):
        np.testing.assert_allclose(m.restrict(field), expected, atol=1e-14)
        assert np.sum(field) * g.dx**2 == pytest.approx(
            np.sum(expected * m.area), rel=1e-14
        )


@pytest.mark.parametrize("n", [31, 32])
def test_leaf_ownership_and_split_face_lengths(n):
    g = grid(n)
    m = LeafMesh(g, mixed(g))
    assert m.area.sum() == g.nx * g.ny * g.dx**2
    for axis in (0, 1):
        select = m.axis == axis
        lengths = np.bincount(
            m.left[select],
            weights=m.length[select] * m.left_real[select],
            minlength=m.n,
        )
        np.testing.assert_allclose(lengths, m.width)
    assert np.any(m.width[m.left] != m.width[m.right])


def test_shared_face_rhs_conserves_mass_and_flat_bed_momentum():
    g = grid()
    solver = AdaptiveSolver(g, params(), fixed_refinement=mixed(g))
    rng = np.random.default_rng(984)
    h = 0.5 + rng.random(solver.mesh.n)
    hu = rng.uniform(-0.2, 0.2, len(h)) * h
    hv = rng.uniform(-0.2, 0.2, len(h)) * h
    rhs, out = solver.leaf_rhs(h, hu, hv, 0.02)
    assert abs(np.dot(rhs[0], solver.mesh.area) + out) < 1e-12
    # Momentum has boundary pressure/advective flux; exercise closed interior
    # redistribution instead with a compact pile and dry physical boundaries.
    s = solver.initial_state(paraboloid(g.x, g.y, 16, 16, 1, 6))
    h, hu, hv = (solver.mesh.restrict(a) for a in (s.h, s.hu, s.hv))
    rhs, out = solver.leaf_rhs(h, hu, hv, 0.02)
    np.testing.assert_allclose(rhs @ solver.mesh.area, 0, atol=1e-12)
    assert out == 0
    assert np.max(np.abs(rhs[0])) > 0


def test_mixed_lake_at_rest_and_repeated_split_merge():
    g = grid()
    x, y = np.meshgrid(g.x, g.y)
    g.b[:] = 2 * np.exp(-((x - 16) ** 2 + (y - 16) ** 2) / 50)
    solver = AdaptiveSolver(g, params(), fixed_refinement=mixed(g))
    s = solver.initial_state(4 - g.b)
    for i in range(30):
        solver.step(s, solver.max_dt(s))
        if i % 3 == 0:
            solver.regrid(s, np.full(solver.mesh.refined.shape, i % 2 == 0))
    assert np.max(np.abs(s.hu)) < 1e-9
    assert np.max(np.abs(s.hv)) < 1e-9
    np.testing.assert_allclose(s.h + g.b, 4, atol=1e-9)


def test_fully_refined_rhs_matches_uniform_muscl():
    g = grid()
    p = params()
    solver = AdaptiveSolver(g, p, fixed_refinement=np.ones((16, 16), dtype=bool))
    uniform = Solver(g, p)
    h = paraboloid(g.x, g.y, 16, 16, 2, 7)
    s = solver.initial_state(h)
    leaves = tuple(solver.mesh.restrict(a) for a in (s.h, s.hu, s.hv))
    rhs, out = solver.leaf_rhs(*leaves, dt=0.01)
    reference = uniform._rhs(s.h, s.hu, s.hv, (slice(0, 32), slice(0, 32)))
    for k in range(3):
        np.testing.assert_allclose(rhs[k][solver.mesh.owner], reference[k], atol=1e-12)
    assert out == reference[3]


@pytest.mark.parametrize("pressure", list(EarthPressure))
def test_fully_refined_rk_stages_match_uniform_on_nonflat_terrain(pressure):
    g = grid(24)
    x, y = np.meshgrid(g.x, g.y)
    g.b[:] = 0.02 * ((x - 12) ** 2 + (y - 12) ** 2)
    p = FlowParams(
        backend=Backend.NUMPY, earth_pressure=pressure, phi_bed_deg=15, phi_int_deg=30
    )
    a = AdaptiveSolver(g, p, fixed_refinement=np.ones((12, 12), dtype=bool))
    b = Solver(g, p)
    h = paraboloid(g.x, g.y, 12, 12, 3, 4)
    sa, sb = a.initial_state(h), b.initial_state(h)
    for _ in range(12):
        dt = min(a.max_dt(sa), b.max_dt(sb))
        a.step(sa, dt)
        b.step(sb, dt)
    for aa, bb in zip((sa.h, sa.hu, sa.hv), (sb.h, sb.hu, sb.hv), strict=True):
        np.testing.assert_allclose(aa, bb, atol=1e-12, rtol=1e-12)


@pytest.mark.parametrize("precision", list(Precision))
def test_mixed_wet_dry_front_outflow_and_mass(precision):
    g = grid()
    solver = AdaptiveSolver(g, params(precision=precision), fixed_refinement=mixed(g))
    s = solver.initial_state(paraboloid(g.x, g.y, 14, 16, 1, 5))
    s.hu[:] = 3 * s.h
    v0 = solver.volume(s.h)
    for frame in solver.run(s, 10, 1):
        assert (frame.h >= 0).all() and np.isfinite(frame.hu).all()
        tolerance = 1e-5 if precision == Precision.FLOAT32 else 1e-8
        assert abs(solver.volume(frame.h) + frame.vol_out - v0) / v0 < tolerance
    assert s.vol_out > 0.1 * v0


def test_delayed_vent_is_refined_and_discrete_volume_is_exact():
    g = grid()
    vent = FluxSource(10, 10, 3, 0.2, start=1, duration=0.7, speed=2)
    solver = AdaptiveSolver(g, params(), [vent])
    s = solver.initial_state(np.zeros_like(g.b))
    frames = list(solver.run(s, 3, 0.5))
    assert frames[2].vol_source == 0
    expected = solver.sources.footprint_volume()
    assert s.vol_source == pytest.approx(expected, rel=1e-12)
    assert solver.volume(s.h) + s.vol_out == pytest.approx(expected, rel=1e-10)
    assert solver.mesh.refined[5, 5]


@pytest.mark.parametrize("pressure", list(EarthPressure))
@pytest.mark.parametrize("rheology", list(Rheology))
def test_numpy_numba_parity(pressure, rheology):
    g = grid(24)
    mask = mixed(g)
    x, y = np.meshgrid(g.x, g.y)
    g.b[:] = 0.05 * ((x - 12) ** 2 + (y - 12) ** 2)
    p = FlowParams(
        backend=Backend.NUMPY,
        earth_pressure=pressure,
        rheology=rheology,
        phi_bed_deg=15,
        phi_int_deg=30,
        curvature=True,
    )
    a = AdaptiveSolver(g, p, fixed_refinement=mask)
    b = AdaptiveSolver(
        g,
        FlowParams(
            backend=Backend.NUMBA,
            earth_pressure=pressure,
            rheology=rheology,
            phi_bed_deg=15,
            phi_int_deg=30,
            curvature=True,
        ),
        fixed_refinement=mask,
    )
    h = paraboloid(g.x, g.y, 12, 12, 1, 4)
    sa, sb = a.initial_state(h), b.initial_state(h)
    for _ in range(12):
        dt = min(a.max_dt(sa), b.max_dt(sb))
        a.step(sa, dt)
        b.step(sb, dt)
    for aa, bb in zip((sa.h, sa.hu, sa.hv), (sb.h, sb.hu, sb.hv), strict=True):
        np.testing.assert_allclose(aa, bb, atol=1e-10, rtol=1e-10)


def test_friction_keeps_a_pile_on_a_shallow_slope():
    from titan3d.core.terrain import inclined_plane

    g = inclined_plane(n=64, dx=10, slope_deg=10)
    p = FlowParams(backend=Backend.NUMPY, phi_bed_deg=20, phi_int_deg=30)
    solver = AdaptiveSolver(g, p)
    h = paraboloid(g.x, g.y, 0, 0, 5, 100)
    s = solver.initial_state(h)
    list(solver.run(s, 20, 20))
    x, _ = np.meshgrid(g.x, g.y)
    shift = np.sum(s.h * x) / s.h.sum() - np.sum(h * x) / h.sum()
    speed = np.hypot(s.hu, s.hv) / np.maximum(s.h, p.h_dry)
    assert abs(shift) < 1
    assert speed.max() < 0.5


def test_draining_limiter_preserves_volume_in_an_oversized_euler_stage():
    g = grid()
    solver = AdaptiveSolver(g, params(), fixed_refinement=mixed(g))
    state = solver.initial_state(paraboloid(g.x, g.y, 16, 16, 1, 5))
    mesh = solver.mesh
    h = mesh.restrict(state.h)
    rhs, out = solver.leaf_rhs(h, 100 * h, np.zeros_like(h), dt=1)
    after = h + rhs[0]
    assert after.min() >= -1e-14
    assert np.dot(after, mesh.area) + out == pytest.approx(
        np.dot(h, mesh.area), rel=1e-12
    )


def test_shared_cfl_accounts_for_both_directions_and_finest_cells():
    from titan3d.core.params import G

    g = grid()
    solver = AdaptiveSolver(g, params(), fixed_refinement=mixed(g))
    state = solver.initial_state(np.full_like(g.b, 2))
    state.hu[:] = 3 * state.h
    state.hv[:] = 4 * state.h
    expected = solver.p.cfl * g.dx / (3 + 4 + 2 * np.sqrt(2 * G))
    assert solver.max_dt(state) == pytest.approx(expected, rel=1e-14)


def test_planar_gravity_acceleration_has_correct_sign_and_units():
    """Independent PDE check: uniform h on a plane gives q_t = -g h b_x."""
    from titan3d.core.params import G

    g = grid()
    slope = 0.2
    g.b[:] = slope * g.x[None, :]
    solver = AdaptiveSolver(g, params(), fixed_refinement=mixed(g))
    mesh = solver.mesh
    h = np.full(mesh.n, 3.0)
    rhs, _ = solver.leaf_rhs(h, np.zeros_like(h), np.zeros_like(h), 0.01)
    interior = (mesh.x > 4) & (mesh.x < 28) & (mesh.y > 4) & (mesh.y < 28)
    np.testing.assert_allclose(rhs[0, interior], 0, atol=1e-13)
    np.testing.assert_allclose(rhs[1, interior], -G * 3 * slope, atol=1e-12)
    np.testing.assert_allclose(rhs[2, interior], 0, atol=1e-12)


def test_ritter_dam_break_across_mixed_interface():
    """Compare with the analytic frictionless dry-bed dam-break solution."""
    from titan3d.core.params import G

    g = Grid(np.zeros((16, 128)), 0.2, x0=-12.7, y0=0.1)
    solver = AdaptiveSolver(g, params(), fixed_refinement=mixed(g))
    initial = np.broadcast_to((g.x < 0).astype(float), g.b.shape).copy()
    state = solver.initial_state(initial)
    v0 = solver.volume(state.h)
    list(solver.run(state, 1, 1))
    c = np.sqrt(G)
    exact = np.where(
        g.x < -c, 1, np.where(g.x > 2 * c, 0, (2 * c - g.x) ** 2 / (9 * G))
    )
    # Declared integrated mean depth error; not a reference generated by the code.
    assert np.mean(np.abs(state.h - exact[None, :])) < 0.015
    assert solver.volume(state.h) + state.vol_out == pytest.approx(v0, rel=1e-10)
    assert np.any(state.h[:, g.x > 0] > 0.1)


def test_adaptation_hysteresis_and_historical_maxima():
    g = grid()
    solver = AdaptiveSolver(g, params())
    state = solver.initial_state(paraboloid(g.x, g.y, 16, 16, 2, 4))
    history = solver.h_max.copy()
    assert solver.mesh.refined.any()
    state.h[:] = state.hu[:] = state.hv[:] = 0
    solver.regrid(state)
    assert solver.mesh.refined.any()
    solver.regrid(state)
    assert solver.mesh.refined.any()
    solver.regrid(state)
    assert not solver.mesh.refined.any()
    np.testing.assert_array_equal(solver.h_max, history)


def test_dynamic_symmetry_and_uniform_fine_accuracy():
    from titan3d.core.stats import frame_stats

    g = grid(48)
    p = params()
    adaptive, uniform = AdaptiveSolver(g, p), Solver(g, p)
    h = paraboloid(g.x, g.y, 24, 24, 2, 6)
    a, b = adaptive.initial_state(h), uniform.initial_state(h)
    list(adaptive.run(a, 2, 2))
    list(uniform.run(b, 2, 2))
    np.testing.assert_allclose(a.h, a.h[::-1, :], atol=1e-10)
    wet = (a.h > 0.1) | (b.h > 0.1)
    assert np.sqrt(np.mean((a.h[wet] - b.h[wet]) ** 2)) <= 0.1 * b.h.max()
    aa, bb = (
        frame_stats(s, g.dx, g.x, g.y, (24, 24), uniform.volume(h), p.h_dry)
        for s in (a, b)
    )
    assert abs(aa.runout - bb.runout) <= 2 * g.dx
    assert abs(aa.area / bb.area - 1) <= 0.1


@pytest.mark.parametrize(
    "field,value",
    [
        ("amr_gradient", 0),
        ("amr_gradient", float("nan")),
        ("amr_buffer", 0),
        ("amr_regrid_every", 0),
        ("amr_coarsen_delay", 0),
    ],
)
def test_invalid_amr_controls_are_rejected(field, value):
    with pytest.raises(ValueError):
        FlowParams(**{field: value})
