# Backend

`backend/` is a [uv](https://docs.astral.sh/uv/) project (Python 3.12) with the package `titan3d` in a src layout.

```bash
cd backend
uv sync                      # install
uv run titan3d serve         # API + UI
uv run pytest                # tests
uv run ruff check --fix src/ && uv run ruff format src/
uvx ty check src/            # type check
```

## Package map

```
src/titan3d/
  core/            pure computation (no web, DB or YAML imports)
  api/             FastAPI app: routes → controllers → core/db, schemas, workers
  db/              SQLite schema and repositories
  cli.py           Click CLI
  config.py        pydantic-settings (TITAN3D_* environment)
  logging.py       loguru setup, stdlib/uvicorn interception
  version.py       package version + git commit (provenance)
```

### `core/`: the model

| Module | Contents |
|---|---|
| `params.py` | `FlowParams` (rheology, φ_bed, φ_int, μ, ξ, earth pressure, curvature, CFL, h_dry, precision, backend), `State` (h, hu, hv, t, step, vol_out, vol_source, wet box), `PileSource`, `FluxSource`, enums |
| `grid.py` | `Grid` (bed, dx, south-west cell centre, CRS) with `x`, `y`, `bounds`, `index_of`, `contains` |
| `numerics.py` | NumPy reference kernels on padded blocks: minmod, MUSCL reconstruction of depth, bed and velocity, hydrostatic reconstruction, Rusanov flux, boundary mass fluxes |
| `kernels_numba.py` | Line-parallel `@njit` versions of the flux, earth-pressure, friction, max-speed, running-max and wet-box kernels |
| `rheology.py` | Savage–Hutter `k_act/k_pas`, earth pressure on a block, implicit Coulomb/Voellmy friction |
| `curvature.py` | Slope cosine and second derivatives; `g_eff = cosθ (g + u·∇∇b·u)` |
| `sources.py` | Paraboloid piles; `FluxSources`, which integrates vent influx exactly over any time step |
| `solver.py` | `Solver`: SSP-RK2 step, CFL and source time-step limits, active window, outflow accounting, per-step maxima, `run()` iterator; `NumpyKernels` / `NumbaKernels` |
| `terrain.py` | Synthetic volcano and inclined plane (tests, demos) |
| `dem.py` | `inspect_tiles`, `stitch_tiles` → `MosaicInfo`, `load_domain` (local UTM, coverage check, gap fill), `preview_grid`, `utm_crs_for`, coordinate transforms |
| `scenario.py` | `Scenario` dataclass, `run_scenario` (frames to disk, progress and cancel callbacks), `Progress`, `RunResult`, `RunCancelled` |
| `stats.py` | `FrameStats` and `frame_stats` (volume fractions, hmax, umax, area, runout) |
| `export.py` | Viewer bundle and terrain preview (quantised, zlib + base64), GeoTIFF writer, inundation GeoJSON and KML |

Use the core directly:

```python
from pathlib import Path
from titan3d.config import Settings
from titan3d.core.dem import load_domain, lonlat_to_xy
from titan3d.core.params import FlowParams, PileSource
from titan3d.core.scenario import Scenario, run_scenario

grid = load_domain(Settings().dems_dir / "semeru/mosaic.tif", (112.9225, -8.108), (6, 16, 14, 6), dx=40)
x, y = lonlat_to_xy(grid.crs, 112.9225, -8.108)
sc = Scenario(grid=grid, params=FlowParams(phi_bed_deg=16), piles=[PileSource(x, y, 60, 300)], t_end=120)
res = run_scenario(sc, Path("out"))
print(res.stats[-1], res.h_max.max())
```

### `api/`: the web layer

| Part | Files | Role |
|---|---|---|
| App | `main.py` | `create_app()`: lifespan (DB init, orphan recovery, built-in DEM registration, dispatcher), CORS, GZip, optional basic auth, frontend serving with cache headers, `AppError` handler |
| Routes | `routes/health.py`, `dems.py`, `simulations.py`, `scenarios.py`, `system.py` | HTTP only: parse, call a controller, return a model or file |
| Controllers | `controllers/dem_controller.py`, `simulation_controller.py`, `scenario_controller.py`, `system_controller.py` | Upload streaming, stitching thread, previews; submit with coverage check, list, cancel, duplicate, delete, artifacts; estimate; YAML; system health (psutil disk/memory/CPU, SQLite probe, queue, Numba, DEM store, storage sizes; cached 5 min; clear regenerable caches) |
| Schemas | `schemas/scenario.py`, `scenario_yaml.py`, `simulation.py`, `dem.py`, `system.py` | `ScenarioRequest` and sub-models, YAML import/export, response models, system health snapshot |
| Workers | `workers/runner.py`, `dispatcher.py` | `execute_run` (shared with the CLI), `worker_main` (child process), `build_bundle`; `Dispatcher` (launch, reap, recover) |
| Errors | `errors.py` | `BadRequest` 400, `NotFound` 404, `Conflict` 409, `PayloadTooLarge` 413, `Unprocessable` 422 |
| DI | `deps.py` | Controllers from `app.state` via `Annotated[..., Depends]` |

### `db/`: persistence

Schema v1 (`database.py`). Each operation opens a short connection in WAL mode with a 30 s busy timeout and foreign keys on.

| Table | Key columns |
|---|---|
| `dems` | id, name, source (`builtin`/`upload`), status (`processing`/`ready`/`failed`), mosaic_path, files_json, info_json (MosaicInfo), error |
| `jobs` | id, name, dem_id, status (`queued`/`running`/`completed`/`failed`/`cancelled`/`interrupted`), scenario_json, provenance_json, grid_json, parent_job_id, pid, timestamps, heartbeat_at, progress columns (sim_t, steps, frames, elapsed_s, eta_s, hmax, umax, runout, area, vol_in_domain, vol_out, released_m3), error, cancel_requested |
| `job_frames` | job_id, k, stats_json |

`repositories.py` (`DemRepository`, `JobRepository`) is the only module that writes SQL. Job claims are atomic (`UPDATE … WHERE status = 'queued'`).

## Run artifacts

`<repo>/data/runs/<id>/` (sibling to `backend/`; override with `TITAN3D_DATA_DIR`):

| File | Content |
|---|---|
| `frames/NNNN.npz` | `h`, `speed` (float32) per output time |
| `grid.npz`, `maxima.npz` | Bed and georeference; per-step maximum depth and speed |
| `stats.json`, `meta.json`, `summary.json` | Frame stats; bundle metadata (sources, parameters, provenance); run summary |
| `max_depth.tif`, `max_speed.tif` | Full-resolution GeoTIFFs in the run's UTM zone |
| `inundation.geojson`, `.kml` | h_max > 0.1 m outline (WGS 84), with area |
| `scenario.yaml`, `run.log` | Reloadable config; solver log |
| `bundle_<N>.json.gz` | Browser playback bundle per detail level, built on demand |

## Configuration

`config.py` reads `TITAN3D_*` environment variables or `backend/.env`:

| Setting | Default | Meaning |
|---|---|---|
| `data_dir` | `<repo>/data` | DB, DEMs, runs, logs; independent of working directory |
| `builtin_dem_dir` / `builtin_dem_id` / `builtin_dem_name` | `<repo>/dem` / `semeru` / `Semeru — DEMNAS 0.27″` | Built-in DEM registration |
| `max_concurrent_runs` | 1 | Parallel worker processes |
| `max_upload_file_mb` / `max_upload_files` | 1024 / 64 | Upload limits |
| `cors_origins` | Vite dev origins | CORS allow-list |
| `frontend_dist` | `<repo>/frontend/dist` | Built UI served at `/` |
| `basic_auth_user` / `basic_auth_password` | unset | Both set → HTTP basic auth (health stays open) |
| `log_level`, `host`, `port` | INFO, 127.0.0.1, 8000 | Logging and defaults |

## CLI

| Command | Purpose |
|---|---|
| `titan3d serve [--host] [--port] [--reload]` | Run the API and UI with uvicorn (`create_app` factory) |
| `titan3d run [-c scenario.yaml] [--dem PATH] [--dx] [--backend] [--precision] [-o OUT]` | Headless run through `execute_run`, with progress lines |
| `titan3d init-config [-o scenario.yaml]` | Commented default scenario |
| `titan3d stitch-dem INPUTS... -o mosaic.tif` | Stitch tiles or folders |
| `titan3d openapi [-o openapi.json]` | Regenerate the committed API schema |

## Tests

`uv run pytest` runs 101 tests. Outputs are written next to the tests as `tests/out_*`, which is git-ignored.

| File | Covers |
|---|---|
| `test_imports.py` | Every module imports in a fresh interpreter (circular imports) |
| `test_solver.py` | Lake at rest, slope at rest, symmetry, mass balance with outflow, active window ≡ full domain, dry skip |
| `test_numba_parity.py` | Numba ≡ NumPy (2 earth-pressure models × curvature), float32 tolerance |
| `test_curvature.py`, `test_sources.py` | Curvature on plane/cylinder/crest; vent volume, timing, direction |
| `test_dem.py` | CRS assumption and rejection, stitching, sentinel nodata, UTM zones, domains, coverage, preview; real Semeru opt-in (`TITAN3D_REAL_DEM=1`) |
| `test_db.py`, `test_scenario_yaml.py` | Job lifecycle, cancel, recovery, concurrency; YAML round trip and field errors, estimate scaling |
| `test_api.py`, `test_openapi.py` | End to end with real worker processes; basic auth; `openapi.json` is current |
| `test_system.py` | System snapshot shape, 5-minute reuse, cache clearing keeps runs and DEMs |

## Working rules

- Lint with ruff, type-check with ty.
- Run `tests/test_imports.py` after any module change.
- Log every finished task in `changelogs/YYYY-mm-dd.md` (local only).
- Branch before changes (`ft/`, `fix/`, `dev/`).
- Use the latest packages.
- Regenerate `openapi.json` (and `npm run gen:api` in the frontend) after schema changes.
