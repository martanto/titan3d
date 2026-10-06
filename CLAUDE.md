# titan3d — project context

Python re-implementation of the Titan2D depth-averaged granular-flow model
(https://github.com/titan2d/titan2d): FastAPI backend + Vite/TypeScript/three.js frontend.
Owner: Anto (PVMBG volcanologist). Work incrementally with small, targeted changes.

## Layout
- `backend/` — uv project, package `titan3d` (src layout)
  - `core/` — pure computation, no web deps: `params`, `grid`, `numerics` (MUSCL-minmod, hydrostatic
    reconstruction with separate h/b reconstruction, Rusanov), `kernels_numba`, `rheology` (Coulomb/Voellmy,
    Savage–Hutter k), `curvature`, `sources` (piles, flux vents), `solver` (SSP-RK2, CFL, active window,
    outflow), `dem` (stitch tiles, local UTM domains), `scenario` (run loop, frames), `stats`, `export`.
  - `api/` — `routes/` (HTTP only) → `controllers/` → core/db; `schemas/` (pydantic; `ScenarioRequest` is the
    single source of truth, YAML in `scenario_yaml.py`); `workers/` (spawned run process + dispatcher).
  - `db/` — SQLite (`dems`, `jobs`, `job_frames`), only `repositories.py` writes SQL.
  - `cli.py` — Click: `serve`, `run`, `init-config`, `stitch-dem`, `openapi`.
  - `openapi.json` — regenerate with `uv run titan3d openapi -o openapi.json` (a test checks it).
- `frontend/` — Vite + TS. `src/scene/engine.ts` (WebGL2; heights in the vertex shader; plan/3D views;
  natural or hillshade surface), `furniture.ts` (graticule, scale bar, north arrow), `ramps.ts`/`cmaps.ts`
  (Crameri maps); `src/ui/*` views (setup, running, results, runs). `npm run gen:api` regenerates API types.
- `dem/` — built-in Semeru DEMNAS tiles. `deploy/` — run docs (uv first, optional Docker). `docs/PLAN.md`.

## Conventions
- Arrays are [j, i] = [y, x]; y increases with j (north up). Grid coordinates are CRS metres (local UTM).
- three.js world in km: X = east, Z = −north, Y = (b − zmin)·vex. Index winding a,b,c / b,d,c (CCW from above).
- Stats per frame: t, steps, vol and vol_out (fractions of released volume), released_m3, hmax, umax,
  area (km², h > 0.1 m), runout (m from the first source).
- UI direction (impeccable): "scientific figure" — see `PRODUCT.md`, `.impeccable/surfaces/frontend-index-html.md`.

## Verified
- Lake at rest, slope at rest, symmetry, mass balance with outflow, active window ≡ full domain,
  Numba ≡ NumPy, curvature, flux sources, DEM stitching, API end to end (`uv run pytest` in backend/).
- Semeru 20 m default domain (1,100 × 1,000): 300 s simulated in ~85 s (Numba, 20 threads).

## Working rules
1. **Log every completed task in the daily changelog.** Any finished task — bug fix, refactor, new feature,
   test, documentation change — must have its outcome recorded in `changelogs/YYYY-mm-dd.md` (today's date)
   before moving on. Create the file if it does not exist. Append; never overwrite previous entries.
   `changelogs/` is git-ignored (local only).
2. **Type checker is `ty`:** `uvx ty check src/` (from `backend/`).
3. **Lint with ruff:** `uv run ruff check --fix src/` (from `backend/`).
4. **All `uv`, `uvx`, and `python` commands are permitted** — no need to ask.
5. **Always create a new branch before any commits or modifications:** `git checkout -b <prefix>/<name>`,
   prefix `fix/` (bug fixes), `ft/` (features), `dev/` (everything else). Never work directly on `main`/`master`.
6. **Test output always goes in `tests/`**, at the same level as the test file that produces it.
7. **Run the circular-import test after every module change:** `uv run pytest tests/test_imports.py -v`.
8. **Frontend work always uses the impeccable and playwright-cli skills.**
9. **Use the latest Python and npm packages** where possible.
10. Progress for the current refactor is tracked in `docs/PLAN.md` (tick items as they finish).
