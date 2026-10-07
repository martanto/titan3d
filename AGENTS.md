# Repository Guidelines

## Project Structure & Module Organization

Titan3d models depth-averaged granular flow with a Python backend and TypeScript/three.js frontend. `backend/src/titan3d/core/` contains computation without web dependencies; `api/` separates routes, controllers, schemas, and workers. Only `db/repositories.py` writes SQL. Backend tests live in `backend/tests/`. Frontend rendering lives in `frontend/src/scene/`, UI views in `frontend/src/ui/`, and styles in `frontend/src/styles/`. Consult `docs/`, `wiki/`, and `deploy/` for design and deployment guidance. Local DEM assets in `dem/` are git-ignored.

## Build, Test, and Development Commands

Run backend commands from `backend/`:

- `uv sync`: install dependencies.
- `uv run titan3d serve --reload`: start the API and serve the built UI.
- `uv run pytest`: run backend tests.
- `uvx ty check src/`: check Python types.
- `uv run ruff check --fix src/` and `uv run ruff format src/`: lint and format.

Run frontend commands from `frontend/`:

- `npm ci`: install locked dependencies.
- `npm run dev`: start Vite with API proxying.
- `npm run build`: check TypeScript and build production assets.

After API schema changes, run `uv run titan3d openapi -o openapi.json` in `backend/`, then `npm run gen:api` in `frontend/`.

## Coding Style & Naming Conventions

Use four-space Python indentation, snake_case functions/modules, and PascalCase classes. Follow existing two-space TypeScript indentation and naming. Keep changes small and targeted. Use existing color tokens and Tailwind v4 utilities. Arrays use `[j, i] = [y, x]`, with north increasing along j; grid coordinates are CRS metres.

## Testing Guidelines

Use pytest files named `test_*.py`. Verify affected numerical invariants and API behavior; no numeric coverage threshold is documented. After every Python module change, run `uv run pytest tests/test_imports.py -v`. Keep generated test output beside its producing test under `tests/`. Validate frontend changes with a build and desktop/mobile, light/dark browser checks using Edge.

## Commit & Pull Request Guidelines

Create a new `fix/`, `ft/`, or `dev/` branch before modifications; never work directly on main/master. History uses concise descriptive subjects, sometimes prefixed by the affected area. PRs should explain the problem, resulting behavior, and validation; link relevant issues and include screenshots for visual changes.

## Agent Working Rules

Always run Astral `ty` for Python type checking and Ruff for linting and formatting checks before completing work: from `backend/`, run `uvx ty check src/`, `uv run ruff check src/`, and `uv run ruff format --check src/`. Resolve any failures caused by your changes. Ruff complements `ty`; it does not perform type checking.

Follow `CLAUDE.md`; frontend work requires impeccable and playwright-cli skills. Append completed outcomes to local `changelogs/YYYY-mm-dd.md`; update `docs/PLAN.md` when completing tracked items. Never commit DEM tiles or local configuration.
