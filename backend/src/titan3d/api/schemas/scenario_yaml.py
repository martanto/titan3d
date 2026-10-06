"""YAML import/export of :class:`ScenarioRequest`.

The file carries a ``schema_version`` and a commented header listing every field
with its unit, so a downloaded config is self-describing and can be edited by
hand, loaded back into the UI, or run with ``titan3d run --config``.
"""

from enum import Enum
from typing import Any
from pathlib import Path

import yaml
from pydantic import BaseModel

from titan3d.version import package_version
from titan3d.api.schemas.scenario import ScenarioRequest


def _field_docs(model: type[BaseModel], prefix: str = "") -> list[str]:
    lines = []
    for name, f in model.model_fields.items():
        ann = f.annotation
        sub = (
            getattr(ann, "__args__", (ann,))[0]
            if name in {"piles", "flux_sources"}
            else ann
        )
        if isinstance(sub, type) and issubclass(sub, BaseModel):
            label = (
                f"{prefix}{name}[]"
                if name in {"piles", "flux_sources"}
                else f"{prefix}{name}"
            )
            lines.append(f"#   {label}:")
            lines.extend(_field_docs(sub, prefix + "  "))
            continue
        desc = f.description or ""
        choices = ""
        if isinstance(ann, type) and issubclass(ann, Enum):
            choices = " (" + " | ".join(str(m.value) for m in ann) + ")"
        lines.append(f"#   {prefix}{name}: {desc}{choices}".rstrip())
    return lines


def scenario_to_yaml(req: ScenarioRequest) -> str:
    """Serialise a scenario to commented YAML."""
    header = [
        "# titan3d scenario configuration",
        f"# written by titan3d {package_version()}",
        "#",
        "# Load it in the web app (Setup → Load config) or run it headless:",
        "#   uv run titan3d run --config this-file.yaml",
        "#",
        "# Fields:",
        *_field_docs(ScenarioRequest),
        "",
    ]
    data: dict[str, Any] = req.model_dump(mode="json")
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=88)
    return "\n".join(header) + body


def scenario_from_yaml(text: str) -> ScenarioRequest:
    """Parse and validate YAML text.

    Raises:
        ValueError: If the text is not a YAML mapping.
        pydantic.ValidationError: If fields are invalid.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("the YAML document must be a mapping of scenario fields")
    return ScenarioRequest.model_validate(data)


def load_scenario_yaml(
    path: Path, overrides: dict[str, Any] | None = None
) -> ScenarioRequest:
    """Read a YAML file, apply ``numerics`` overrides (dx, backend, precision)."""
    req = scenario_from_yaml(path.read_text(encoding="utf-8"))
    if overrides:
        data = req.model_dump(mode="json")
        data["numerics"] = {**data["numerics"], **overrides}
        req = ScenarioRequest.model_validate(data)
    return req
