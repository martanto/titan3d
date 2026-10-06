"""Scenario helpers: defaults, estimates, YAML import/export."""

from pydantic import ValidationError

from titan3d.api.schemas.scenario import ScenarioRequest
from titan3d.api.schemas.simulation import ImportErrorItem, ScenarioImportOut
from titan3d.api.schemas.scenario_yaml import scenario_to_yaml, scenario_from_yaml


class ScenarioController:
    """Business logic for scenario endpoints."""

    def default(self) -> ScenarioRequest:
        """The default Semeru scenario."""
        return ScenarioRequest()

    def export_yaml(self, req: ScenarioRequest) -> str:
        """Commented YAML for a scenario."""
        return scenario_to_yaml(req)

    def import_yaml(self, text: str) -> ScenarioImportOut:
        """Parse YAML, returning field-level errors instead of raising."""
        try:
            return ScenarioImportOut(ok=True, scenario=scenario_from_yaml(text))
        except ValidationError as exc:
            errors = [
                ImportErrorItem(
                    loc=".".join(str(p) for p in e["loc"]) or "(root)", msg=e["msg"]
                )
                for e in exc.errors()
            ]
            return ScenarioImportOut(ok=False, errors=errors)
        except ValueError as exc:
            return ScenarioImportOut(
                ok=False, errors=[ImportErrorItem(loc="(file)", msg=str(exc))]
            )
