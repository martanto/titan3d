"""Command-line interface for titan3d, built on Click.

Commands:
    titan3d stitch-dem   Stitch GeoTIFF tiles into one mosaic.
    titan3d run          Run a scenario headless from a YAML config.
    titan3d serve        Start the FastAPI server.
    titan3d openapi      Write the OpenAPI schema to a JSON file.

Heavy modules are imported inside each command so ``titan3d --help`` stays fast
and importing this module never pulls in the solver or the web stack.
"""

import json
from pathlib import Path

import click

from titan3d import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="titan3d")
def main() -> None:
    """titan3d: Titan2D-style granular-flow modelling."""


@main.command("stitch-dem")
@click.argument(
    "inputs",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "-o",
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output mosaic GeoTIFF.",
)
def stitch_dem(inputs: tuple[Path, ...], out_path: Path) -> None:
    """Stitch GeoTIFF tiles (files or directories of *.tif) into one mosaic."""
    from titan3d.core.dem import stitch_tiles

    paths: list[Path] = []
    for item in inputs:
        paths.extend(sorted(item.glob("*.tif")) if item.is_dir() else [item])
    if not paths:
        raise click.UsageError("No .tif files found in the given inputs.")
    info = stitch_tiles(paths, out_path)
    click.echo(f"wrote {out_path} ({len(paths)} tiles)")
    click.echo(json.dumps(info.to_dict(), indent=2, default=str))


@main.command("init-config")
@click.option(
    "-o",
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("scenario.yaml"),
    show_default=True,
    help="Output YAML file.",
)
def init_config(out_path: Path) -> None:
    """Write the default Semeru scenario as a commented YAML template."""
    from titan3d.api.schemas.scenario import ScenarioRequest
    from titan3d.api.schemas.scenario_yaml import scenario_to_yaml

    out_path.write_text(scenario_to_yaml(ScenarioRequest()), encoding="utf-8")
    click.echo(f"wrote {out_path}")


def _resolve_mosaic(dem: Path | None, out_dir: Path) -> Path:
    """Mosaic GeoTIFF from ``--dem`` (file or tile directory) or the built-in DEM."""
    from titan3d.config import get_settings
    from titan3d.core.dem import stitch_tiles

    settings = get_settings()
    if dem is not None and dem.is_file():
        return dem
    tiles_dir = dem if dem is not None else settings.builtin_dem_dir
    cached = (
        out_dir / "mosaic.tif"
        if dem is not None
        else settings.dems_dir / settings.builtin_dem_id / "mosaic.tif"
    )
    if cached.exists():
        return cached
    tiles = sorted(
        p for p in tiles_dir.glob("*") if p.suffix.lower() in {".tif", ".tiff"}
    )
    if not tiles:
        raise click.UsageError(f"No GeoTIFF tiles in {tiles_dir}.")
    click.echo(f"stitching {len(tiles)} tile(s) from {tiles_dir} …")
    stitch_tiles(tiles, cached)
    return cached


@main.command("run")
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Scenario YAML file (default: the built-in Semeru scenario).",
)
@click.option(
    "--dem",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Mosaic GeoTIFF or directory of tiles (default: built-in DEM).",
)
@click.option(
    "-o",
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory for run artifacts (default: data/runs/cli-<timestamp>).",
)
@click.option("--dx", type=float, default=None, help="Override grid spacing (m).")
@click.option(
    "--backend",
    type=click.Choice(["numba", "numpy"]),
    default=None,
    help="Override the compute backend.",
)
@click.option(
    "--precision",
    type=click.Choice(["float64", "float32"]),
    default=None,
    help="Override floating-point precision.",
)
def run(
    config_path: Path | None,
    dem: Path | None,
    out_dir: Path | None,
    dx: float | None,
    backend: str | None,
    precision: str | None,
) -> None:
    """Run a scenario headless and write its artifacts to OUT."""
    from titan3d.logging import setup_logging
    from titan3d.core.scenario import Progress
    from titan3d.api.workers.runner import execute_run
    from titan3d.api.schemas.scenario import ScenarioRequest
    from titan3d.api.schemas.scenario_yaml import load_scenario_yaml

    overrides = {
        k: v
        for k, v in {"dx": dx, "backend": backend, "precision": precision}.items()
        if v is not None
    }
    if config_path is not None:
        req = load_scenario_yaml(config_path, overrides=overrides)
    else:
        req = ScenarioRequest()
        if overrides:
            req = ScenarioRequest.model_validate(
                {
                    **req.model_dump(),
                    "numerics": {**req.numerics.model_dump(), **overrides},
                }
            )
    if out_dir is None:
        from datetime import datetime

        from titan3d.config import get_settings

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = get_settings().runs_dir / f"cli-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging("INFO", out_dir / "run.log")
    mosaic = _resolve_mosaic(dem, out_dir)

    def progress(p: Progress) -> None:
        latest = p.latest
        extra = (
            f"  hmax {latest.hmax:6.1f} m  umax {latest.umax:5.1f} m/s  "
            f"runout {latest.runout:7.0f} m"
            if latest
            else ""
        )
        eta = f"  eta {p.eta_s / 60:5.1f} min" if p.eta_s is not None else ""
        click.echo(
            f"t = {p.sim_t:7.1f}/{p.t_end:.0f} s  steps {p.steps:6d}  "
            f"wall {p.elapsed_s:7.1f} s{eta}{extra}"
        )

    summary = execute_run(
        req, mosaic, out_dir, dem_name=str(mosaic), on_progress=progress
    )
    click.echo(json.dumps(summary, indent=2))


@main.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--reload", is_flag=True, help="Auto-reload on code changes (dev).")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the FastAPI server with uvicorn."""
    import uvicorn

    uvicorn.run(
        "titan3d.api.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


@main.command("openapi")
@click.option(
    "-o",
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("openapi.json"),
    show_default=True,
    help="Output JSON file.",
)
def openapi(out_path: Path) -> None:
    """Write the OpenAPI schema of the API to a JSON file."""
    from titan3d.api.main import create_app

    spec = create_app().openapi()
    text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    out_path.write_text(text, encoding="utf-8")
    click.echo(f"wrote {out_path}")


if __name__ == "__main__":
    main()
