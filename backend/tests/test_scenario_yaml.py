"""Scenario YAML round trip and validation."""

import pytest
from pydantic import ValidationError

from titan3d.api.schemas.scenario import FluxSourceIn, ScenarioRequest
from titan3d.api.schemas.scenario_yaml import (
    scenario_to_yaml,
    scenario_from_yaml,
    load_scenario_yaml,
)
from titan3d.api.controllers.scenario_controller import ScenarioController


def test_round_trip_is_identical() -> None:
    req = ScenarioRequest(
        name="Round trip",
        flux_sources=[FluxSourceIn(influx=2.0, duration=30.0, speed=5.0)],
    )
    text = scenario_to_yaml(req)
    assert text.startswith("# titan3d scenario configuration")
    assert "phi_bed_deg: Basal friction angle [deg]" in text
    assert "(coulomb | voellmy)" in text
    assert scenario_from_yaml(text) == req


def test_overrides_apply_to_numerics(out_path) -> None:
    p = out_path("scenario.yaml")
    p.write_text(scenario_to_yaml(ScenarioRequest()), encoding="utf-8")
    req = load_scenario_yaml(p, {"dx": 40.0, "precision": "float32"})
    assert req.numerics.dx == 40.0
    assert req.numerics.precision.value == "float32"


def test_validation_errors_are_reported_per_field() -> None:
    bad = "name: x\nmaterial:\n  phi_bed_deg: 95\nnumerics:\n  dx: 2\n"
    out = ScenarioController().import_yaml(bad)
    assert not out.ok
    locs = {e.loc for e in out.errors}
    assert "material.phi_bed_deg" in locs and "numerics.dx" in locs


def test_not_a_mapping_and_invalid_yaml() -> None:
    assert not ScenarioController().import_yaml("- 1\n- 2\n").ok
    assert not ScenarioController().import_yaml("a: [unclosed\n").ok


def test_needs_a_source() -> None:
    with pytest.raises(ValidationError, match="at least one pile or flux source"):
        ScenarioRequest(piles=[])


def test_estimate_scales_with_resolution() -> None:
    from titan3d.api.controllers.simulation_controller import estimate

    coarse = estimate(ScenarioRequest.model_validate({"numerics": {"dx": 40}}))
    fine = estimate(ScenarioRequest.model_validate({"numerics": {"dx": 20}}))
    assert fine.cells == pytest.approx(4 * coarse.cells, rel=0.01)
    assert fine.grid_shape == (1000, 1100)
