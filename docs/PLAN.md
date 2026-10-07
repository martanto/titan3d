# titan3d — backend (FastAPI) + frontend (Vite/TS/three.js) refactor, Semeru DEM

## Colima example extension
- [x] Critique and polish Examples: prominent responsive load flow, themed controls, accessible validation, and locked upload state; verified desktop/tablet/mobile in both themes.
- [x] Add an Examples page with pinned Titan2D Colima DEM/source links, Coulomb and Voellmy presets, upload-to-Setup flow, and explicit adaptation notes. See `COLIMA.md`.

## Context
`granflow` (now `titan3d`) is a NumPy port of Titan2D's depth-averaged granular-flow solver with a single-file three.js viewer. It runs on a synthetic cone, and a CLI writes a JSON file that gets baked into an HTML page. The goal is a real app:
- a **FastAPI backend** (`backend/`) that keeps the calculation core separate from the API layer and runs long, high-resolution simulations on the **stitched Semeru DEMNAS mosaic** or on user-uploaded DEMs;
- a **Node/Vite frontend** (`frontend/`) where the user sets up a scenario, sees a loading animation while it runs, and plays back the result in 3D.

Decisions so far:
- Vite + TypeScript frontend; full scenario form (click terrain to place the pile or vent).
- Users are PVMBG analysts, researchers and the public.
- **High resolution is the priority:** default 20 m grid; runs from tens of minutes up to hours are acceptable, as with Titan2D.
- The old core may be **fully rewritten**. Jobs are tracked in **SQLite**. The API schema goes in **`openapi.json`**.
- **Multi-file DEM upload.** Semeru is the built-in dataset.
- **Primary way to run is plain uv + uvicorn, no Docker required:** `uv run titan3d serve` serves the API *and* the built frontend (`frontend/dist`) on one port. Docker Compose is an optional extra for server installs.
- In scope too: **Numba + float32**, **bed curvature + vent (flux) sources**, **run provenance + GeoJSON/KML + outflow tracking**, **CI + optional Docker deploy**, and **scenario config download/upload in YAML**.

Facts checked:
- DEM: 5 DEMNAS tiles, 3333² float32, 0.27″ ≈ 8.3 m pixels, **no CRS set** (EPSG:4326 implied), nodata NaN.
- Coverage: 112.75–113.25°E, 8.5–7.75°S. The SE tile (113.0–113.25°E, 8.5–8.25°S) is **missing**. Semeru (~112.922°E, 8.108°S) and the Besuk Kobokan channel to the SE are covered.
- `backend/pyproject.toml` has no dependencies yet and references `README.md` and `LICENSE`, neither of which exists under `backend/`. `ruff.toml` first-party is already `titan3d`. `ty.toml` roots at `./src`. `deploy/` and `frontend/` are empty.
- Tools: uv 0.11.7, Node 22 / npm 10. Image converter: ffmpeg only (no image generator, so impeccable runs code-first).

## Working rules (apply throughout; written into `CLAUDE.md` in Phase 0)
1. **Daily changelog.** Every finished task (fix, refactor, feature, test, docs) is appended to `changelogs/YYYY-mm-dd.md` with today's date before moving on. Create the file if missing, never overwrite entries. `changelogs/` is git-ignored.
2. **Type check:** `uvx ty check src/` (from `backend/`).
3. **Lint:** `uv run ruff check --fix src/` (from `backend/`).
4. All `uv` / `uvx` / `python` commands run without asking.
5. **Branch first:** `git checkout -b ft/fastapi-backend-frontend` before any modification. Never work on `main`.
6. **Test output goes in `tests/`**, at the same level as the test file. Fixtures, tiny GeoTIFFs and temp DBs go there too, never in the project root.
7. **Circular-import test** after every module add/remove/reorg: `uv run pytest tests/test_imports.py -v`. The test walks `titan3d` with `pkgutil.walk_packages` and imports each module in a fresh subprocess.
8. **Frontend work always uses impeccable and playwright-cli.**
9. **Latest packages:** `uv add <pkg>` without upper pins, and `npm install <pkg>@latest`. three.js moves from the old r147 UMD build to current ES modules (`three/addons/controls/OrbitControls.js`). Numba may hold NumPy one minor version back. If so, I'll accept the newest compatible pair that uv resolves and note it in the changelog.

## Target layout
```
backend/
  pyproject.toml  ruff.toml  ty.toml  README.md  openapi.json (generated, committed)  Dockerfile (optional)
  src/titan3d/
    core/                      # pure computation; never imports fastapi/pydantic/sqlite
      params.py                # FlowParams, State, PileSource, FluxSource, Precision (float32/64), Backend (numpy/numba)
      numerics.py              # minmod, velocity, MUSCL + hydrostatic reconstruction, Rusanov flux (NumPy reference)
      kernels_numba.py         # @njit(parallel, fastmath=False, cache=True) equivalents of the flux/friction kernels
      rheology.py              # Coulomb / Voellmy implicit friction incl. curvature term, Savage–Hutter k
      curvature.py             # bed curvature κ_xx, κ_yy, κ_xy from the DEM
      sources.py               # paraboloid pile (initial), Titan2D-style flux (vent) sources (time-dependent)
      solver.py                # Solver: rhs, SSP-RK2, CFL dt, run iterator, active window, outflow accounting
      terrain.py               # synthetic_volcano (tests/demo)
      dem.py                   # inspect/stitch tiles, CRS, crop + reproject to local UTM, fill nodata -> Grid; sha256
      scenario.py              # Scenario dataclass -> grid + sources -> run loop, frame writer, progress/cancel hooks
      stats.py                 # per-frame t, vol_in_domain, vol_out, hmax, umax, area, runout, steps
      export.py                # viewer bundle; GeoTIFF max depth/speed; GeoJSON + KML inundation outline
      config_io.py             # Scenario <-> YAML-ready dict (versioned schema; no pydantic)
    api/
      main.py                  # create_app(): CORS, GZip, lifespan (DB init, register built-in DEM, dispatcher)
      routes/                  # health.py, dems.py, simulations.py, scenarios.py (thin: HTTP only)
      controllers/             # dem_controller.py, simulation_controller.py, scenario_controller.py
      schemas/                 # pydantic models (ScenarioRequest is the single source of truth for validation)
      workers/runner.py        # child-process entry: runs core.scenario, writes progress to SQLite
    db/
      database.py              # sqlite3 factory (WAL, busy_timeout, foreign keys), migrations on startup
      repositories.py          # JobRepository, DemRepository (only module that writes SQL)
    config.py                  # pydantic-settings (TITAN3D_* env): data_dir, builtin_dem_dir, db_path, limits, CORS
    logging.py                 # loguru setup + intercept uvicorn/stdlib logging
    version.py                 # package version + git commit (env override for Docker builds)
    cli.py                     # titan3d stitch-dem | run [--config x.yaml] | serve | openapi
  tests/                       # test_imports, test_solver, test_numba_parity, test_curvature, test_sources,
                               # test_dem, test_db, test_config_io, test_api, test_openapi (+ outputs here)
data/                          # gitignored, project root: titan3d.db, dems/<id>/, runs/<id>/, logs/
frontend/                      # Vite + TS, three, pako (YAML handled server-side); `npm run build` -> dist/ served by FastAPI
deploy/                        # OPTIONAL: docker-compose.yml, .env.example, nginx/, README
.github/workflows/ci.yml
```

## Phase 0 — Branch, rules, progress tracker
- `git checkout -b ft/fastapi-backend-frontend`. The existing staged changes come along.
- Copy this plan to **`docs/PLAN.md`** in the repo. Its **Progress tracker** checklist (below) is ticked `[x]` as each item finishes, alongside the changelog entry.
- Add the working rules to `CLAUDE.md`, add `changelogs/` to `.gitignore`, and create `changelogs/2026-10-06.md`.

## Progress tracker
- **Roadmap prerequisites — storage layout**
  - [x] Move default runtime storage to project-root `data/`, preserve existing DEM paths and run artifacts, update deployment and documentation, and verify regressions.
- **Phase 0 — Setup**
  - [x] Create branch `ft/fastapi-backend-frontend`
  - [x] Add `docs/PLAN.md`
  - [x] Add working rules to `CLAUDE.md`; update `.gitignore`; start the changelog
- **Phase 1 — Backend scaffold**
  - [x] pyproject deps (latest) + scripts + `backend/README.md`; `uv sync`
  - [x] `config.py`, `logging.py` (loguru), `version.py`
  - [x] `tests/test_imports.py` (circular imports)
- **Phase 2 — Core rewrite**
  - [x] `params`, `numerics`, `rheology`, `solver`, `terrain`, `stats`, `scenario`, `export`
  - [x] Active-window computation + outflow accounting
  - [x] Verification tests (lake at rest, slope at rest, symmetry, mass balance, active window ≡ full domain)
  - [x] Old/new regression check → delete `src/` and `run_demo.py`
- **Phase 3 — Numba + float32**
  - [x] `kernels_numba.py` + backend switch
  - [x] Precision option
  - [x] Parity/tolerance tests + benchmark logged
- **Phase 4 — Curvature + vent sources**
  - [x] `curvature.py` + normal-stress term + tests
  - [x] `sources.py` flux sources + tests
- **Phase 5 — DEM**
  - [x] `inspect_tiles`, `stitch_tiles` (CRS assignment, sha256)
  - [x] `load_domain` (local UTM, NaN checks)
  - [x] Stitch Semeru mosaic; DEM tests
- **Phase 6 — Jobs + SQLite**
  - [x] `db/database.py` + `repositories.py` (dems, jobs, job_frames, provenance)
  - [x] Worker process + dispatcher + cancel + interrupted recovery
  - [x] Artifacts: bundle, GeoTIFFs, GeoJSON/KML, scenario.yaml; DB tests
- **Phase 7 — API**
  - [x] Schemas, controllers, routes (health, dems, simulations, scenarios)
  - [x] YAML import/export (`api/schemas/scenario_yaml.py`; YAML is pydantic-validated so it lives outside `core`) + CLI `--config`
  - [x] `openapi.json` + staleness test; API end-to-end tests
  - [x] Real Semeru run at dx 20 (timed) + dx 60 smoke run
- **Phase 8 — Frontend**
  - [x] impeccable init → `PRODUCT.md`
  - [x] impeccable audit + critique of `viewer/template.html` (reports shared)
  - [x] Vite + TS scaffold, generated API types, typed client
  - [x] Setup view (DEM picker/upload, terrain preview, sources, form, YAML)
  - [x] Running view (loading animation, progress, cancel)
  - [x] Results view (GPU playback, stats, provenance, downloads, duplicate)
  - [x] impeccable detect + playwright batch (desktop/mobile, light/dark) + fixes
- **Phase 9 — Run without Docker, CI, optional Docker**
  - [x] `.github/workflows/ci.yml`
  - [x] FastAPI serves `frontend/dist` (SPA fallback) so `uv run titan3d serve` is the whole app
  - [x] Optional HTTP basic auth in FastAPI (`TITAN3D_BASIC_AUTH_USER/PASSWORD`, off by default)
  - [x] README quick start: uv + uvicorn first (Windows/Linux/macOS), Docker last as optional
  - [x] (Optional) Dockerfiles + `deploy/docker-compose.yml` + README
- **Phase 10 — Cleanup + docs**
  - [x] Remove `viewer/`
  - [x] Update `README.md` and `CLAUDE.md`; update roadmap

## Phase 1 — Backend scaffold
- Deps (latest): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `python-multipart`, `loguru`, `numpy`, `numba`, `rasterio`, `pyyaml`.
- Test group gets `httpx`. Add the `[project.scripts] titan3d = "titan3d.cli:main"` entry and `backend/README.md`.
- Drop the `license` field until a LICENSE exists. SQLite uses the stdlib `sqlite3`.
- Add `logging.py` (loguru to stderr and a rotating `data/logs/titan3d.log`, with uvicorn logs intercepted), `config.py` and `version.py`.

## Phase 2 — Rewrite the core (learn from `src/titan3d/`, then delete it)
- **Same scheme, cleaner code:** MUSCL-minmod, hydrostatic reconstruction (Audusse), Rusanov, SSP-RK2, CFL dt, implicit friction, Savage–Hutter k. Rheology/pressure/precision/backend become `Enum`s. The CFL wave speed now includes k. Full type hints, Google docstrings, ruff/ty clean.
- **Regression check before deleting:** compare old and new solvers on a small demo grid with curvature off. They should agree to ~1e-10, or any difference should be explained by a deliberate fix. Then `git rm -r src/ run_demo.py`.
- **Active window:** compute only on the bounding box of wet cells, any active vent footprint, and a 3-cell margin. Results stay identical, which a test confirms.
- **Outflow accounting:** sum the boundary mass flux each step. Stats report `vol_in_domain`, `vol_out` and the source volume added, so mass balance closes: in-domain + out = released.

## Phase 3 — Speed: Numba + float32
- `kernels_numba.py` mirrors the NumPy reference kernels (directional flux update, friction) as `@njit(parallel=True, cache=True)` loops over the active window. The solver picks the backend through `FlowParams.backend`, defaulting to `numba` with a fallback to `numpy` if the import fails.
- `Precision.FLOAT32 | FLOAT64`, defaulting to float64 for verification. With float32, the arrays and kernels are typed float32, but mass sums stay float64.
- Tests: Numba results match NumPy (float64, ~1e-12) on the demo and on a curvature case. float32 conserves mass to ~1e-5 and its runout matches float64 within one cell.
- Benchmark: log cells/s for NumPy vs Numba at 20 m in the changelog.

## Phase 4 — Physics: bed curvature + vent sources
- **Curvature** (`curvature.py`, used in `rheology.py`): κ comes from DEM second derivatives, normalised by the slope metric. The normal stress becomes `h (g cosθ + u·κ·u)`, clamped at ≥ 0, matching Titan2D's centripetal term. It's switchable (`curvature: bool`, default on). Tests: zero on a plane, and the correct sign/magnitude on an analytic cylinder bed.
- **Flux (vent) sources** (`sources.py`), Titan2D style: centre (lon/lat or local x/y), radius, influx rate (m/s of height), start time, duration, optional initial speed and direction. Influx is added each step with a paraboloid spatial profile. Scenarios have zero or more piles plus zero or more flux sources, and at least one source in total. Tests: injected volume equals rate × area-integral × duration, and nothing happens before the start or after the end time.

## Phase 5 — DEM stitching (`core/dem.py`)
- `inspect_tiles(paths)`: checks single band and numeric type. When the CRS is missing, assume EPSG:4326 only if the bounds are valid lon/lat, otherwise reject clearly. Tiles in a different CRS are warped to the first tile's CRS.
- `stitch_tiles(paths, out)`: `rasterio.merge` with nodata NaN, written as a deflate-compressed, tiled GeoTIFF. It returns bounds, CRS, resolution, shape, NaN fraction, highest point and a **sha256** of the mosaic. Semeru gives ~6666×9999 with the SE tile left NaN. The same code serves the built-in `dem/` set (stitched once at startup) and uploads.
- `load_domain(mosaic, vent_lonlat, extents_km, dx) -> Grid`: reprojects to the **local UTM zone picked from the vent** (EPSG:32749 for Semeru), bilinear, rows flipped so `j` increases north, small NaN gaps filled by nearest neighbour. Domains with more than 0.5% NaN are rejected with an error naming the gap.
- Semeru default: pile at the summit crater (~112.922°E, 8.108°S, refined to the DEM summit area); extents W 6 / E 16 / N 6 / S 14 km at **dx = 20 m** (~1100×1000 cells). The minimum dx is 10 m (native ~8.3 m).

## Phase 6 — Background jobs tracked in SQLite
- Runs execute in a separate **spawned process**. A dispatcher in the API lifespan starts queued jobs up to `max_concurrent_runs` (default 1).
- **SQLite** (`data/titan3d.db`, WAL):
  - `dems`: id, name, source, status, bounds, crs, res, shape, nan_frac, summit, sha256, error, created_at.
  - `jobs`: id, dem_id, status (queued/running/completed/failed/cancelled/interrupted), scenario_json, **provenance** (titan3d version, git commit, dem sha256, backend, precision, numpy/numba versions), pid, timestamps, sim_t, t_end, steps, elapsed_s, eta_s, hmax, umax, runout, vol_in_domain, vol_out, error, cancel_requested, `parent_job_id` (set when a run is duplicated).
  - `job_frames`: per-frame stats, for live sparklines.
- The worker writes progress every ~2 s and checks `cancel_requested` every step. On startup, `running` jobs whose pid is gone are marked `interrupted`.
- Artifacts in `data/runs/<id>/`:
  - `frames/NNNN.npz`, `bundle.json.gz` (downsampled to ≤ ~640 per side for the browser);
  - `max_depth.tif`, `max_speed.tif` (full resolution, DEM CRS);
  - `inundation.geojson` + `inundation.kml` (h_max > threshold, default 0.1 m; marching-squares outline in EPSG:4326, holes kept);
  - `scenario.yaml`, `run.log`.

## Phase 7 — API (routes → controllers → core) + openapi.json + YAML
- `GET /api/health`
- **DEMs:** `GET /api/dems` · `POST /api/dems` (multipart **multiple GeoTIFFs** + name; streamed with size/type limits; stitched in the background) · `GET /api/dems/{id}` · `GET /api/dems/{id}/preview?max_cells=` · `DELETE /api/dems/{id}` (uploads only)
- **Simulations:**
  - `POST /api/simulations` (`ScenarioRequest`: dem_id, piles[], flux_sources[], rheology, φ_bed, φ_int, μ, ξ, pressure, curvature, dx, extents, t_end, output_every, cfl, backend, precision) → `202 {id}`
  - `GET /api/simulations` · `GET /api/simulations/{id}` (status, progress, provenance)
  - `POST /api/simulations/{id}/duplicate` (re-queues with the same scenario, `parent_job_id` set)
  - `POST /api/simulations/{id}/cancel` · `DELETE /api/simulations/{id}`
  - Downloads: `/result` (bundle), `/geotiff/{max_depth|max_speed}`, `/inundation.{geojson|kml}`, **`/config.yaml`**
- **YAML config:** `POST /api/scenarios/export` (ScenarioRequest → `scenario.yaml` download, for the current form before running) and `POST /api/scenarios/import` (YAML upload → validated ScenarioRequest, field-level errors returned). The YAML has a `schema_version` and comments with units. The CLI reads the same file: `titan3d run --config scenario.yaml`.
- Controllers translate pydantic ↔ `core` dataclasses and call the repositories. `core` never sees pydantic or SQL.
- **`openapi.json`:** `titan3d openapi` writes `backend/openapi.json`. Endpoints carry tags, summaries and response models. A test fails if the file is stale. The frontend runs `npm run gen:api` (`openapi-typescript`) → `src/api/schema.d.ts`.

## Phase 8 — Frontend (impeccable + playwright workflow)
Both skills are already loaded this session.
1. **impeccable init** → `PRODUCT.md`: platform web, stack Vite+TS, users analysts/researchers/public. Inferred facts are labelled. Code-first build.
2. **impeccable audit** and **critique** of `viewer/template.html`. Both reports go to you before the rebuild.
3. **Polish + rebuild** in the incumbent world (survey-paper palette, Archivo/IBM Plex Mono, oxide-red accent, light/dark), extended to the new surfaces. Every finding gets fixed. Read `craft-floor.md` before UI edits.
4. Structure: `api/` (generated types + typed client), `data/decode.ts`, `scene/` (terrain, flow, ramps, camera, probe, source markers), `ui/` (dem-picker/upload, scenario form, yaml import/export, run progress, playback, stats, legend, sparklines, run history), `main.ts`. Vite proxies `/api` in dev.
5. Views:
   - **Setup:**
     - DEM picker: built-in Semeru, or multi-file drag-and-drop **upload** with per-file progress and stitching status/errors.
     - Terrain preview: click to place piles and vents, with the domain outline shown.
     - Parameter form: friction, rheology, curvature, dx, precision, backend, duration. Shows estimated volume, cell count and a runtime class.
     - **Resolution option:** presets Quick 40 m / Standard 20 m (default) / Fine 10 m / Custom (10–200 m; minimum 10 m because the DEMNAS pixel is ~8.3 m). A live estimate shows grid size, cell count, memory and runtime class (halving dx ≈ 8× runtime). A separate viewer-detail setting (default ≤ 640 cells per side) controls only the 3D playback; GeoTIFF / GeoJSON downloads always use the full computed resolution.
     - **Download config (YAML)** and **Load config (YAML)**.
   - **Running — loading animation:** progress tied to sim time, steps, elapsed/ETA, live hmax/runout and vol in/out, plus a cancel button. Polls the job. Reduced-motion variant. You can leave and return through history.
   - **Results:** 3D playback (depth/speed/max modes, timeline, probe, H/L, sparklines incl. outflow) and a provenance panel. Downloads: GeoTIFFs, GeoJSON/KML, **config YAML**. **Duplicate run** button.
6. three.js: flow displacement and colour run in the vertex shader from R8 frame textures, interpolated on the GPU.
7. Finish: `impeccable detect --json` once. One playwright-cli batch (desktop + mobile, light + dark, console). Fix in one batch, then at most one confirm round.

## Phase 9 — Run without Docker (default), CI, optional Docker
- **No-Docker path is the default and fully supported.** Requirements: uv (Python is fetched by uv) and, only to build the UI, Node.
  - `cd backend && uv sync && uv run titan3d serve` → API + UI at `http://127.0.0.1:8000` (`--host 0.0.0.0 --port N` for LAN use; `--reload` for dev). Equivalent: `uv run uvicorn titan3d.api.main:create_app --factory`.
  - `create_app()` mounts `frontend/dist` (path from `TITAN3D_FRONTEND_DIST`, default `<repo>/frontend/dist`) as static files with an SPA fallback, skipped with a log hint if `dist/` is absent (API-only mode). Dev mode keeps Vite on :5173 with the `/api` proxy.
  - Rasterio and Numba ship binary wheels for Windows/Linux/macOS, so no GDAL or compiler install is needed.
  - Optional protection without nginx: FastAPI basic-auth dependency enabled when `TITAN3D_BASIC_AUTH_USER` and `TITAN3D_BASIC_AUTH_PASSWORD` are set (constant-time compare); `/api/health` stays open.
  - Long runs keep going in the worker process; on Windows the worker uses `spawn`, so no extra service manager is needed. `deploy/README.md` documents running as a service (NSSM on Windows, systemd unit on Linux) as plain text, not required.
- **Docker is optional.** Nothing in the backend, frontend, tests or CI depends on it.
- `.github/workflows/ci.yml`:
  - **backend job:** uv; `uv sync`, ruff check + format check, `uvx ty check src/`, pytest (Numba cache dir set), openapi staleness check.
  - **frontend job:** Node LTS; `npm ci`, `npm run gen:api` with a git diff check, `tsc`, `npm run build`.
- *(Optional)* `backend/Dockerfile`: multi-stage uv image, non-root user, runs `titan3d serve`. Mounts `data/` and the built-in DEM directory read-only.
- *(Optional)* `frontend/Dockerfile`: Node build → nginx static.
- *(Optional)* `deploy/docker-compose.yml`: `api` and `web` (nginx serving dist, proxying `/api`, **HTTP basic auth** via htpasswd from `.env`, upload size limit matching the backend), plus named volumes for data. `deploy/README.md` covers setup and creating the htpasswd user. In Docker, auth can sit at nginx or reuse the FastAPI basic-auth setting.

## Phase 10 — Cleanup and docs
- Remove `src/` and `run_demo.py` (Phase 2) and `viewer/` once the frontend matches it.
- `.gitignore`: add `data/`, `.cache/`, `frontend/node_modules/`, `frontend/dist/`, `.idea/`, `changelogs/`, `deploy/.env`.
- Update `README.md` and `CLAUDE.md` (layout, commands, API, YAML format, deploy). Move the remaining items to the roadmap: parameter sweeps/probabilistic maps, AMR, Pitman–Le two-phase, internal-friction shear term.

## Verification
- From `backend/`, after every change: `uv run ruff check --fix src/`, `uv run ruff format src/`, `uvx ty check src/`, `uv run pytest tests/test_imports.py -v`.
- `uv run pytest` (outputs in `tests/`):
  - Solver physics: lake at rest; pile on 10° slope with φ 20° stays put; symmetry; mass balance (in-domain + outflow = released, 1e-5).
  - Speedups: active window ≡ full domain; Numba ≡ NumPy; float32 tolerance.
  - Physics additions: curvature on plane/cylinder; flux-source volume and timing.
  - DEM: mosaic shape/bounds/CRS assignment/sha256; Semeru domain has no NaN; out-of-coverage domain rejected.
  - SQLite: lifecycle, WAL concurrency, interrupted recovery, provenance stored, duplicate run.
  - YAML: round-trip (Scenario → YAML → Scenario identical); bad YAML gives field errors.
  - API end-to-end with TestClient on a tiny run: DEM upload (2 tiles), submit, progress, result, GeoTIFF, GeoJSON/KML, config.yaml, duplicate, cancel.
  - `openapi.json` is up to date.
- Old/new solver regression check before deleting `src/`.
- Real runs: `uv run titan3d run --dx 20` on default Semeru (Numba, timing logged), plus a dx 60 smoke run. Open the GeoTIFF and GeoJSON with rasterio and json to check bounds and CRS.
- Frontend: `npm run build`. With both servers running, use playwright-cli to: upload 2 DEM tiles, place a pile and a vent, download the YAML and load it back, submit a dx 60 run, watch the loading animation, play the result, use probe, modes, downloads and duplicate. Then screenshots (desktop + mobile, light/dark) with no console errors.
- No-Docker: after `npm run build`, `uv run titan3d serve` alone serves UI + API on :8000. playwright-cli loads `/`, runs a dx 60 scenario end-to-end, and checks basic auth prompts only when the env vars are set. A test covers the SPA fallback and auth on/off with TestClient.
- Optional Docker: `docker compose -f deploy/docker-compose.yml up --build`. Check that basic auth prompts, then that `/api/health` and the UI load through nginx. The CI workflow is validated with `act`, if installed, or on first push.
