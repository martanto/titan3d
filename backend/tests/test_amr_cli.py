"""CLI mesh overrides reach the same validated request as API and YAML."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from titan3d import cli
from titan3d.api.workers import runner
from titan3d.api.schemas.scenario import ScenarioRequest
from titan3d.api.schemas.scenario_yaml import scenario_to_yaml


@pytest.mark.parametrize("flag,expected", [("--amr", True), ("--no-amr", False)])
def test_cli_mesh_flag_overrides_yaml(monkeypatch, out_path, flag, expected):
    request = ScenarioRequest.model_validate({"numerics": {"amr": not expected}})
    config = out_path("amr-cli.yaml")
    config.write_text(scenario_to_yaml(request), encoding="utf-8")
    received = []
    monkeypatch.setattr(cli, "_resolve_mosaic", lambda *_: Path("unused.tif"))
    monkeypatch.setattr(
        runner, "execute_run", lambda req, *args, **kwargs: received.append(req) or {}
    )
    monkeypatch.setattr("titan3d.logging.setup_logging", lambda *_: None)
    result = CliRunner().invoke(
        cli.main,
        ["run", "--config", str(config), "--out", str(out_path("amr-cli-run")), flag],
    )
    assert result.exit_code == 0, result.output
    assert received[0].numerics.amr is expected
