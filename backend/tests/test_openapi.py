"""The committed openapi.json must match the application."""

import json
from pathlib import Path

from titan3d.api.main import create_app
from tests.test_api import make_settings


SPEC = Path(__file__).resolve().parents[1] / "openapi.json"


def test_openapi_json_is_up_to_date() -> None:
    current = create_app(make_settings("openapi")).openapi()
    committed = json.loads(SPEC.read_text(encoding="utf-8"))
    assert committed == current, "run `uv run titan3d openapi -o openapi.json`"


def test_openapi_covers_all_endpoints() -> None:
    paths = json.loads(SPEC.read_text(encoding="utf-8"))["paths"]
    for p in (
        "/api/health",
        "/api/dems",
        "/api/dems/{dem_id}/preview",
        "/api/simulations",
        "/api/simulations/{job_id}/result",
        "/api/simulations/{job_id}/files/{name}",
        "/api/simulations/{job_id}/duplicate",
        "/api/scenarios/export",
        "/api/scenarios/import",
        "/api/scenarios/estimate",
    ):
        assert p in paths, p
