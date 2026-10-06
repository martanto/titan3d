"""Scenario endpoints: defaults, cost estimate, YAML export/import."""

from typing import Annotated

from fastapi import File, APIRouter, UploadFile
from fastapi.responses import PlainTextResponse

from titan3d.api.deps import ScenariosDep
from titan3d.api.errors import BadRequest
from titan3d.api.schemas.scenario import RESOLUTION_PRESETS, ScenarioRequest
from titan3d.api.schemas.simulation import ScenarioEstimate, ScenarioImportOut
from titan3d.api.controllers.simulation_controller import estimate


router = APIRouter(prefix="/scenarios", tags=["scenarios"])

MAX_YAML_BYTES = 256 * 1024


@router.get("/default", summary="Default scenario (Semeru summit collapse)")
def default_scenario(scenarios: ScenariosDep) -> ScenarioRequest:
    """A ready-to-run scenario with sensible defaults."""
    return scenarios.default()


@router.get("/presets", summary="Grid-spacing presets [m]")
def resolution_presets() -> dict[str, float]:
    """Quick / standard / fine grid spacing."""
    return RESOLUTION_PRESETS


@router.post("/estimate", summary="Estimate grid size, memory and runtime")
def estimate_scenario(req: ScenarioRequest) -> ScenarioEstimate:
    """Rough cost of a scenario before submitting it."""
    return estimate(req)


@router.post(
    "/export",
    summary="Scenario as YAML",
    response_class=PlainTextResponse,
    responses={200: {"content": {"application/x-yaml": {}}}},
)
def export_scenario(req: ScenarioRequest, scenarios: ScenariosDep) -> PlainTextResponse:
    """Commented YAML for the given scenario (download)."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in req.name)[:60]
    return PlainTextResponse(
        scenarios.export_yaml(req),
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f'attachment; filename="{safe or "scenario"}.yaml"'
        },
    )


@router.post("/import", summary="Validate an uploaded YAML config")
async def import_scenario(
    scenarios: ScenariosDep,
    file: Annotated[UploadFile, File(description="Scenario YAML")],
) -> ScenarioImportOut:
    """Parse a YAML config; returns field-level errors instead of failing."""
    raw = await file.read(MAX_YAML_BYTES + 1)
    if len(raw) > MAX_YAML_BYTES:
        raise BadRequest("Config files are limited to 256 KB.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequest("Config must be UTF-8 text.") from exc
    return scenarios.import_yaml(text)
