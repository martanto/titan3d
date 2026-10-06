"""Flux (vent) sources."""

import numpy as np

from titan3d.core.params import Backend, FlowParams, FluxSource
from titan3d.core.solver import Solver
from titan3d.core.terrain import inclined_plane


def make_solver(src: FluxSource) -> Solver:
    grid = inclined_plane(n=80, dx=10.0, slope_deg=20.0)
    return Solver(grid, FlowParams(phi_bed_deg=15.0, backend=Backend.NUMPY), [src])


def test_injected_volume_matches_rate_and_duration() -> None:
    src = FluxSource(x=150.0, y=0.0, radius=60.0, influx=0.5, start=2.0, duration=6.0)
    solver = make_solver(src)
    s = solver.initial_state(np.zeros_like(solver.b))
    frames = list(solver.run(s, t_end=12.0, output_every=1.0))
    by_t = {round(f.t, 6): f for f in frames}
    expected = solver.sources.footprint_volume()
    assert abs(expected - src.volume) / src.volume < 0.02  # discrete vs analytic
    assert by_t[2.0].vol_source == 0.0
    assert by_t[1.0].h.sum() == 0.0
    assert abs(by_t[5.0].vol_source - expected / 2) / expected < 1e-12
    assert abs(by_t[12.0].vol_source - expected) / expected < 1e-12
    final = frames[-1]
    assert abs(solver.volume(final.h) + final.vol_out - expected) / expected < 1e-6


def test_source_initial_velocity_direction() -> None:
    src = FluxSource(x=0.0, y=0.0, radius=50.0, influx=0.2, start=0.0, duration=5.0,
                     speed=10.0, direction_deg=0.0)  # due north
    solver = make_solver(src)
    s = solver.initial_state(np.zeros_like(solver.b))
    s = solver.step(s, 0.1)
    assert s.hv.sum() > 0
    assert abs(s.hu.sum()) < 1e-12
