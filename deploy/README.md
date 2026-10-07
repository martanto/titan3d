# Running titan3d

titan3d runs from one command with [uv](https://docs.astral.sh/uv/). Docker is optional.

## 1. Run with uv (default; Windows, Linux, macOS)

Requirements: **uv**, which fetches Python 3.12 for you. **Node 22+** is needed only to build the UI once. Rasterio and Numba install as binary wheels, so GDAL and a compiler are not required.

```bash
# build the web UI once (and after each frontend change)
cd frontend
npm ci
npm run build

# start API + UI on http://127.0.0.1:8000
cd ../backend
uv sync
uv run titan3d serve
```

- **Network access:** `uv run titan3d serve --host 0.0.0.0 --port 8000` makes it reachable from other machines on the network.
- **First start:** the built-in Semeru DEM is stitched once, which takes about 20 s.
- **Data location:** runs, uploads and the SQLite database live in `data/`.
- **Development:** run `uv run titan3d serve --reload` in `backend/`, and `npm run dev` in `frontend/`. Vite serves the UI on http://localhost:5173 and proxies `/api` to the backend.

### Settings

Settings are environment variables, or a `backend/.env` file:

| Variable | Default | Meaning |
|---|---|---|
| `TITAN3D_DATA_DIR` | `<repo>/data` | DB, uploaded DEMs, run outputs, logs; independent of working directory |
| `TITAN3D_BUILTIN_DEM_DIR` | `<repo>/dem` | GeoTIFF tiles registered as the built-in DEM |
| `TITAN3D_MAX_CONCURRENT_RUNS` | `1` | Simulations run in parallel (each uses all cores) |
| `TITAN3D_BASIC_AUTH_USER` / `_PASSWORD` | unset | Both set → HTTP basic auth on UI and API (`/api/health` stays open) |
| `TITAN3D_FRONTEND_DIST` | `<repo>/frontend/dist` | Built UI served at `/` |

### Moving existing data

The default data folder is now `<repo>/data`, a sibling of `backend/`.
For installations using the previous `<repo>/backend/data` default:

1. Stop the API server and all workers. Back up the data folder, including SQLite
   sidecar files if present. Do not move a database while it is open.
2. Move `backend/data` to `data` at the repository root. Do not merge into an
   existing destination; choose which dataset to retain first.
3. From `backend/`, rebase the absolute DEM paths stored in the moved database:

   ```bash
   uv run python -c "from pathlib import Path; from titan3d.db.repositories import DemRepository; root=Path.cwd().parent; print(DemRepository(root/'data'/'titan3d.db').relocate_paths(root/'backend'/'data', root/'data'))"
   ```

4. Update any `TITAN3D_DATA_DIR` override that points to the old folder. A relative
   override is resolved from the process working directory; use an absolute path
   to avoid ambiguity. Restart and verify the DEM list and existing run downloads.

External DEM paths and relative tile filenames are preserved. Run IDs, scenarios,
provenance and artifacts are unchanged. Docker keeps the same named data volume,
now mounted at `/app/data`; stored paths from `/app/backend/data` likewise need
rebasing to `/app/data` with all app containers stopped before normal startup.

### Keep it running as a service (optional)

- **Windows** ([NSSM](https://nssm.cc/)): set the service to start `uv` in the `backend` folder:
  ```
  nssm install titan3d "C:\Users\<you>\.local\bin\uv.exe" "run titan3d serve --host 0.0.0.0"
  nssm set titan3d AppDirectory D:\Projects\titan3d\backend
  ```
- **Linux** (systemd): create `/etc/systemd/system/titan3d.service`:
  ```ini
  [Service]
  WorkingDirectory=/opt/titan3d/backend
  ExecStart=/usr/local/bin/uv run titan3d serve --host 0.0.0.0
  Restart=on-failure
  User=titan3d
  [Install]
  WantedBy=multi-user.target
  ```

Runs execute in separate worker processes. A run that is in progress when the server stops is marked *interrupted*; start it again from the Runs list with **Run again**.

## 2. Docker (optional)

```bash
cp deploy/.env.example deploy/.env    # optional: basic auth, limits
docker compose -f deploy/docker-compose.yml up --build
```

The image builds the frontend and serves API + UI on port 8000. Data persists in the `titan3d-data` volume; the repository's `dem/` folder is mounted read-only as the built-in DEM.
