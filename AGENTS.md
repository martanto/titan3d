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
    Experimental opt-in AMR: `amr_mesh` (one-level 2:1 leaf ownership and conservative water-fill transfers),
    `amr` (shared split-face MUSCL/hydrostatic fluxes, draining limiter, SSP-RK2, dynamic regridding;
    Numba neighbour/scatter kernels). `dx` is finest spacing; output remains on that regular grid.
    See `docs/AMR-DESIGN.md` and `docs/AMR-VERIFICATION.md`; uniform solver remains the default.
  - `api/` — `routes/` (HTTP only) → `controllers/` → core/db; `schemas/` (pydantic; `ScenarioRequest` is the
    single source of truth, YAML in `scenario_yaml.py`); `workers/` (spawned run process + dispatcher).
    `main.py` serves `frontend/dist` (index.html `no-cache`, hashed assets `immutable`).
  - `db/` — SQLite (`dems`, `jobs`, `job_frames`), only `repositories.py` writes SQL.
  - System health: `api/controllers/system_controller.py` (psutil; reading cached 5 min, `?refresh=true`;
    clear regenerable previews/bundles) → `GET /api/system`, `POST /api/system/caches/clear`.
  - `cli.py` — Click: `serve`, `run`, `init-config`, `stitch-dem`, `openapi`.
  - `openapi.json` — regenerate with `uv run titan3d openapi -o openapi.json` (a test checks it), then
    `npm run gen:api` in `frontend/`.
- `frontend/` — Vite + TypeScript (TS pinned ~6.0 for openapi-typescript) + three.js + **Tailwind CSS v4**.
  - `src/scene/engine.ts` (WebGL2; heights in the vertex shader; plan (ortho, north-up) / 3D views; Natural
    DEM-derived or Hillshade surface; envelope with release footprint masked; plan-only threshold outline),
    `furniture.ts` (graticule, scale bar + north arrow lower left, labelled index contours avoiding data/labels),
    `ramps.ts`/`cmaps.ts` (Crameri batlow/imola/lajolla-reversed).
  - `src/ui/*` views: setup (DEM upload, click-to-place sources, pile volume entry), running, results
    (presenter mode, export figure, copy caption), runs, system (health page, not realtime); `stage.ts` (surface context: Natural on terrain views,
    Hillshade under data).
  - Styling: `styles/tokens.css` (light/dark tokens) + `styles/app.css` = `@import "tailwindcss"`, `@theme inline`
    mapping tokens (default palette removed), `@layer base` / `@layer components`; utilities in `src/ui/*.ts` for
    layout and one-offs. Never add colours outside the tokens.
- `data/` — runtime storage at the project root, sibling to `backend/`: `titan3d.db`,
  uploaded/stitched DEMs in `dems/`, run artifacts in `runs/`, and `logs/` (local only,
  git-ignored; never commit). Default is independent of cwd; `TITAN3D_DATA_DIR` overrides it.
- `dem/` — built-in DEM tiles (local only, git-ignored; never commit them). `deploy/` — run docs (uv first),
  `nginx.conf.example`, optional Docker. `docs/` — `PLAN.md`, design reviews. `wiki/` — Home, Titan2D,
  Terminology, Architecture, Backend, Frontend, API-Reference (+ `_Sidebar.md`).
- Design records: `PRODUCT.md`, `DESIGN.md`, `.impeccable/design.json`, `.impeccable/surfaces/frontend-index-html.md`
  (direction contract), `.impeccable/critique/`. Local-only: `.impeccable/review/`, `config.local.json`, `hook.cache.json`.

## Conventions
- Arrays are [j, i] = [y, x]; y increases with j (north up). Grid coordinates are CRS metres (local UTM).
- three.js world in km: X = east, Z = −north, Y = (b − zmin)·vex. Index winding a,b,c / b,d,c (CCW from above).
- Stats per frame: t, steps, vol and vol_out (fractions of released volume), released_m3, hmax, umax,
  area (km², h > 0.1 m), runout (m from the first source).
- UI direction (impeccable): "scientific figure" — true depth and VE 1× by default, every exaggeration badged,
  captions state what is shown (incl. "synthesised from the DEM, not imagery" and "not an official hazard map").

## Status
- Backend, frontend, CI (`.github/workflows/ci.yml`), docs and wiki complete; `docs/PLAN.md` fully ticked.
- UI: impeccable audit/critique of the old viewer (9/20, 20/40) → rebuilt; finish review **ship** after three
  verdict passes (material fixes only). Open headroom: 3D axis box, hazard-map-style inundation outline,
  elevation zoning in the Natural surface.
- Branches: `ft/fastapi-backend-frontend` (pushed); `ft/tailwind-nginx-wiki` (Tailwind v4, nginx, wiki).

## Verified
- Lake at rest, slope at rest, symmetry, mass balance with outflow, active window ≡ full domain,
  Numba ≡ NumPy, curvature, flux sources, DEM stitching, API end to end, system health (`uv run pytest` in backend/, 101 tests).
- Semeru 20 m default domain (1,100 × 1,000): 300 s simulated in ~85 s (Numba, 20 threads).
- Frontend: `npm run build` (tsc + vite), impeccable detector clean, playwright-cli captures (desktop/mobile,
  light/dark; use `--browser=msedge`, Chrome is not installed).

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
   Before creating the branch, ensure the working tree is clean, run `git fetch origin`, switch to `main`,
   and update it with `git merge --ff-only origin/main`. Create the new branch from this updated `main`
   to reduce PR conflicts. If the fast-forward fails, resolve the divergence before branching; never
   discard local work or reset `main` automatically.
6. **Test output always goes in `tests/`**, at the same level as the test file that produces it.
7. **Run the circular-import test after every module change:** `uv run pytest tests/test_imports.py -v`.
8. **Frontend work always uses the impeccable and playwright-cli skills.**
9. **Use the latest Python and npm packages** where possible.
10. Progress for the current refactor is tracked in `docs/PLAN.md` (tick items as they finish).
