# titan3d backend

FastAPI service and calculation core for titan3d, a Python re-implementation of the
[Titan2D](https://github.com/titan2d/titan2d) depth-averaged granular-flow model.

```bash
uv sync                      # install
uv run titan3d serve         # API on http://127.0.0.1:8000 (docs at /docs)
uv run titan3d run --config scenario.yaml   # headless run
uv run pytest                # tests
```

- `src/titan3d/core/` — solver, rheology, DEM handling, exports (no web dependencies)
- `src/titan3d/api/`  — FastAPI routes, controllers, schemas, background worker
- `src/titan3d/db/`   — SQLite job and DEM tracking

See the repository root `README.md` for the model description.
