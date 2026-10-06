# API Reference

The web app and any script use the same JSON API.

| | |
|---|---|
| Base URL | `http://<host>:8000/api` (same origin as the UI) |
| Interactive docs | `/api/docs` (Swagger UI) |
| Schema | `/api/openapi.json`; committed copy: `backend/openapi.json` (a test keeps it current) |
| Auth | None by default. With `TITAN3D_BASIC_AUTH_USER/PASSWORD` set, HTTP basic auth on everything except `GET /api/health`. |
| Errors | JSON `{"detail": "…"}` with 400 (bad input), 404 (unknown id), 409 (wrong state, e.g. DEM not ready), 413 (upload too large), 422 (validation, or domain outside DEM coverage). Pydantic validation errors return `detail` as a list of `{loc, msg}`. |
| Compression | JSON responses over 2 KB are gzip-encoded. Result and preview bundles are served pre-compressed (`Content-Encoding: gzip`). |

Regenerate the schema after backend changes with `uv run titan3d openapi -o openapi.json`, and the frontend types with `npm run gen:api`.

## Examples

```bash
API=http://127.0.0.1:8000/api

# health and DEMs
curl -s $API/health
curl -s $API/dems

# upload several GeoTIFF tiles as one DEM, then poll until status is "ready"
curl -s -F name="Merapi DEMNAS" -F files=@tile1.tif -F files=@tile2.tif $API/dems
curl -s $API/dems/dem-1a2b3c4d5e

# start from the default scenario, change it, estimate, submit
curl -s $API/scenarios/default > s.json          # edit s.json (dem_id, piles, material…)
curl -s -H 'Content-Type: application/json' -d @s.json $API/scenarios/estimate
curl -s -H 'Content-Type: application/json' -d @s.json $API/simulations   # → {"id": "a9544b45015c", …}

# progress, frame stats, cancel
curl -s $API/simulations/a9544b45015c | jq '.status, .progress'
curl -s $API/simulations/a9544b45015c/frames
curl -s -X POST $API/simulations/a9544b45015c/cancel

# outputs of a completed run
curl -s -o max_depth.tif   $API/simulations/a9544b45015c/files/max_depth.tif
curl -s -o inundation.kml  $API/simulations/a9544b45015c/files/inundation.kml
curl -s --compressed       $API/simulations/a9544b45015c/result?max_cells=640 > bundle.json

# YAML
curl -s -H 'Content-Type: application/json' -d @s.json $API/scenarios/export > scenario.yaml
curl -s -F file=@scenario.yaml $API/scenarios/import          # → {"ok": true, "scenario": {…}} or field errors
```

Python:

```python
import time
import httpx   # uv add httpx (or use requests)

api = "http://127.0.0.1:8000/api"
s = httpx.get(f"{api}/scenarios/default").json()
s["material"]["phi_bed_deg"] = 16
s["numerics"]["dx"] = 40
job = httpx.post(f"{api}/simulations", json=s).json()["id"]
while (j := httpx.get(f"{api}/simulations/{job}").json())["status"] in ("queued", "running"):
    print(f'{j["progress"]["fraction"]:.0%}  runout {j["progress"]["runout"]}')
    time.sleep(2)
print(j["status"], j["artifacts"])
```

## Polling and lifecycle

Job statuses run `queued` → `running` → `completed`. A job can also end `failed`, `cancelled` or `interrupted` (server stopped).

- Poll `GET /simulations/{id}` every 1–2 s. `progress.fraction` is the simulated-time fraction.
- `progress.eta_s` is a naive estimate: elapsed time scaled by the remaining simulated time.
- `grid` and `provenance` appear once the worker has built the domain.

## Bundle format (`/result`, `/dems/{id}/preview`)

```jsonc
{
  "meta": {
    "nx": 367, "ny": 333, "dx": 60.0,            // display grid (may be reduced: "stride")
    "x0": 706080.0, "y0": 9089500.0,             // south-west cell centre, CRS metres
    "crs": "EPSG:32749", "zmin": 213.4, "zmax": 3650.1,
    "nframes": 61, "every": 2.0, "hmax": 59.0, "vmax": 94.5,
    "sources": [{"kind": "pile", "x": …, "y": …, "radius": 300, "height": 60, "lon": …, "lat": …}],
    "provenance": {…}, "title": "…", "rheology": "coulomb", "phi_bed": 24, …
  },
  "stats": [{"t": 0, "steps": 0, "vol": 1.0, "vol_out": 0, "released_m3": 8.48e6,
             "hmax": 59.0, "umax": 0, "area": 0.28, "runout": 300}, …],
  "terrain":   "<base64 zlib uint16 LE>",    // z = zmin + q/65535·(zmax−zmin), row 0 = south
  "depth":     "<base64 zlib uint8[nframes·nx·ny]>",   // h = (q/255)²·hmax
  "speed":     "<base64 zlib uint8[nframes·nx·ny]>",   // |u| = q/255·vmax
  "hmaxField": "<base64 zlib uint8[nx·ny]>"            // max depth over every step, sqrt-quantised
}
```

Previews carry `terrain` plus `valid`, a bit-packed mask of cells with DEM data, and metadata (`name`, `summit`, `bounds_lonlat`, `res_m`).

## Endpoints

| Method | Path | Summary | Request | Success response |
|---|---|---|---|---|
| `GET` | `/api/health` | Service health and version | — | 200 HealthOut |
| `GET` | `/api/dems` | List DEMs | — | 200 array of DemOut |
| `POST` | `/api/dems` | Upload GeoTIFF tiles (stitched in the background) | multipart form | 202 DemOut |
| `GET` | `/api/dems/{dem_id}` | DEM metadata and stitching status | — | 200 DemOut |
| `DELETE` | `/api/dems/{dem_id}` | Delete DEM | — | 204  |
| `GET` | `/api/dems/{dem_id}/preview` | Terrain preview bundle (gzipped JSON) | query `max_cells` | 200 application/json |
| `POST` | `/api/simulations` | Queue a simulation | ScenarioRequest | 202 SimulationCreated |
| `GET` | `/api/simulations` | List simulations | query `limit` | 200 array of SimulationOut |
| `GET` | `/api/simulations/{job_id}` | Simulation status and progress | — | 200 SimulationOut |
| `DELETE` | `/api/simulations/{job_id}` | Delete a simulation | — | 204  |
| `GET` | `/api/simulations/{job_id}/frames` | Per-frame statistics so far | — | 200 array of FrameStatsOut |
| `POST` | `/api/simulations/{job_id}/cancel` | Cancel a simulation | — | 200 SimulationOut |
| `POST` | `/api/simulations/{job_id}/duplicate` | Run the same scenario again | — | 202 SimulationCreated |
| `GET` | `/api/simulations/{job_id}/result` | Viewer bundle (gzipped JSON) | query `max_cells` | 200 application/json |
| `GET` | `/api/simulations/{job_id}/files/{name}` | Download an artifact | — | 200  |
| `GET` | `/api/scenarios/default` | Default scenario (Semeru summit collapse) | — | 200 ScenarioRequest |
| `GET` | `/api/scenarios/presets` | Grid-spacing presets [m] | — | 200 object |
| `POST` | `/api/scenarios/estimate` | Estimate grid size, memory and runtime | ScenarioRequest | 200 ScenarioEstimate |
| `POST` | `/api/scenarios/export` | Scenario as YAML | ScenarioRequest | 200 text/plain |
| `POST` | `/api/scenarios/import` | Validate an uploaded YAML config | multipart form | 200 ScenarioImportOut |

## Schemas

### ScenarioRequest

A complete simulation configuration.

| Field | Type | Default | Description |
|---|---|---|---|
| `schema_version` | `1` | `1` |  |
| `name` | string | `Semeru summit collapse` |  |
| `dem_id` | string | `semeru` |  |
| `piles` | array of PileIn |  |  |
| `flux_sources` | array of FluxSourceIn |  |  |
| `domain` | DomainIn |  |  |
| `material` | MaterialIn |  |  |
| `numerics` | NumericsIn |  |  |
| `t_end` | number | `300.0` | Simulated time [s] (> 0.0, ≤ 86400.0) |
| `output_every` | number | `2.0` | Output interval [s] (> 0.0, ≤ 3600.0) |

### PileIn

Paraboloid pile released at ``t = 0``.

| Field | Type | Default | Description |
|---|---|---|---|
| `lon` | number | `112.9225` | Longitude [deg] (≥ -180.0, ≤ 180.0) |
| `lat` | number | `-8.108` | Latitude [deg] (≥ -90.0, ≤ 90.0) |
| `height` | number | `60.0` | Peak thickness H [m] (> 0.0, ≤ 1000.0) |
| `radius` | number | `300.0` | Radius R [m] (> 0.0, ≤ 10000.0) |

### FluxSourceIn

Titan2D-style flux (vent) source.

| Field | Type | Default | Description |
|---|---|---|---|
| `lon` | number | `112.9225` | Longitude [deg] (≥ -180.0, ≤ 180.0) |
| `lat` | number | `-8.108` | Latitude [deg] (≥ -90.0, ≤ 90.0) |
| `radius` | number | `100.0` | Footprint radius [m] (> 0.0, ≤ 5000.0) |
| `influx` | number | `1.0` | Peak extrusion rate at the centre [m/s] (> 0.0, ≤ 50.0) |
| `start` | number | `0.0` | Start time [s] (≥ 0.0) |
| `duration` | number | `60.0` | Duration [s] (> 0.0) |
| `speed` | number | `0.0` | Initial speed [m/s] (≥ 0.0, ≤ 200.0) |
| `direction_deg` | number | `0.0` | Initial direction, clockwise from north [deg] (≥ 0.0, < 360.0) |

### DomainIn

Computational domain around an anchor point.

| Field | Type | Default | Description |
|---|---|---|---|
| `center_lon` | number \| null |  | Anchor longitude; defaults to the first source |
| `center_lat` | number \| null |  | Anchor latitude; defaults to the first source |
| `west_km` | number | `6.0` | Extent west of anchor [km] (> 0.0, ≤ 100.0) |
| `east_km` | number | `16.0` | Extent east of anchor [km] (> 0.0, ≤ 100.0) |
| `south_km` | number | `14.0` | Extent south [km] (> 0.0, ≤ 100.0) |
| `north_km` | number | `6.0` | Extent north [km] (> 0.0, ≤ 100.0) |

### MaterialIn

Material model.

| Field | Type | Default | Description |
|---|---|---|---|
| `rheology` | Rheology | `coulomb` |  |
| `phi_bed_deg` | number | `24.0` | Basal friction angle [deg] (> 0.0, < 60.0) |
| `phi_int_deg` | number | `34.0` | Internal friction angle [deg] (> 0.0, < 60.0) |
| `mu` | number | `0.12` | Voellmy friction coefficient (> 0.0, < 1.0) |
| `xi` | number | `1000.0` | Voellmy turbulence coefficient [m/s²] (> 0.0, ≤ 10000.0) |
| `earth_pressure` | EarthPressure | `savage-hutter` |  |
| `curvature` | boolean | `True` | Bed-curvature (centripetal) term |

### NumericsIn

Grid and solver settings.

| Field | Type | Default | Description |
|---|---|---|---|
| `dx` | number | `20.0` | Grid spacing [m] (DEMNAS pixel ≈ 8.3 m) (≥ 10.0, ≤ 500.0) |
| `cfl` | number | `0.4` | Courant number (> 0.05, ≤ 0.9) |
| `backend` | Backend | `numba` |  |
| `precision` | Precision | `float64` |  |
| `h_dry` | number | `0.001` | Dry threshold [m] (> 0.0, ≤ 0.1) |

### SimulationCreated

Response to a submitted simulation.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | string | *required* |  |
| `status` | `queued` \| `running` \| `completed` \| `failed` \| `cancelled` \| `interrupted` | *required* |  |
| `estimated_cells` | integer | *required* |  |
| `grid_shape` | array of object | *required* |  |

### SimulationOut

A simulation job.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | string | *required* |  |
| `name` | string | *required* |  |
| `dem_id` | string | *required* |  |
| `status` | `queued` \| `running` \| `completed` \| `failed` \| `cancelled` \| `interrupted` | *required* |  |
| `scenario` | ScenarioRequest | *required* |  |
| `progress` | ProgressOut | *required* |  |
| `provenance` | object \| null |  |  |
| `grid` | GridOut \| null |  |  |
| `parent_job_id` | string \| null |  |  |
| `created_at` | string | *required* |  |
| `started_at` | string \| null |  |  |
| `finished_at` | string \| null |  |  |
| `error` | string \| null |  |  |
| `cancel_requested` | boolean | `False` |  |
| `artifacts` | array of string |  | Downloadable artifact names |

### ProgressOut

Live progress of a run.

| Field | Type | Default | Description |
|---|---|---|---|
| `fraction` | number | *required* | Completed fraction of simulated time (0–1) |
| `sim_t` | number | *required* | Simulated time [s] |
| `t_end` | number | *required* |  |
| `steps` | integer | *required* |  |
| `frames` | integer | *required* |  |
| `elapsed_s` | number | *required* |  |
| `eta_s` | number \| null | *required* |  |
| `hmax` | number \| null |  | Max depth in the latest frame [m] |
| `umax` | number \| null |  | Max speed in the latest frame [m/s] |
| `runout` | number \| null |  | Runout in the latest frame [m] |
| `area` | number \| null |  | Inundated area [km²] |
| `vol_in_domain` | number \| null |  | Fraction of released volume |
| `vol_out` | number \| null |  | Fraction that left the domain |
| `released_m3` | number \| null |  |  |

### GridOut

Computational grid of a run.

| Field | Type | Default | Description |
|---|---|---|---|
| `nx` | integer | *required* |  |
| `ny` | integer | *required* |  |
| `dx` | number | *required* |  |
| `x0` | number | *required* |  |
| `y0` | number | *required* |  |
| `crs` | string \| null | *required* |  |
| `bounds` | array of number | *required* |  |
| `bounds_lonlat` | array of number \| null | *required* |  |
| `zmin` | number | *required* |  |
| `zmax` | number | *required* |  |

### FrameStatsOut

Statistics of one output frame.

| Field | Type | Default | Description |
|---|---|---|---|
| `t` | number | *required* |  |
| `steps` | integer | *required* |  |
| `vol` | number | *required* |  |
| `vol_out` | number | *required* |  |
| `released_m3` | number | *required* |  |
| `hmax` | number | *required* |  |
| `umax` | number | *required* |  |
| `area` | number | *required* |  |
| `runout` | number | *required* |  |

### ScenarioEstimate

Cost estimate for a scenario before running it.

| Field | Type | Default | Description |
|---|---|---|---|
| `grid_shape` | array of object | *required* |  |
| `cells` | integer | *required* |  |
| `memory_mb` | number | *required* | Approximate peak memory of the solver [MB] |
| `released_m3` | number | *required* |  |
| `frames` | integer | *required* |  |
| `runtime_class` | `seconds` \| `minutes` \| `tens of minutes` \| `hours` | *required* |  |

### ScenarioImportOut

Result of importing a YAML config.

| Field | Type | Default | Description |
|---|---|---|---|
| `ok` | boolean | *required* |  |
| `scenario` | ScenarioRequest \| null |  |  |
| `errors` | array of ImportErrorItem |  |  |

### ImportErrorItem

One field-level validation problem in an imported config.

| Field | Type | Default | Description |
|---|---|---|---|
| `loc` | string | *required* |  |
| `msg` | string | *required* |  |

### DemOut

A registered DEM.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | string | *required* |  |
| `name` | string | *required* |  |
| `source` | `builtin` \| `upload` | *required* |  |
| `status` | `processing` \| `ready` \| `failed` | *required* |  |
| `files` | array of string | *required* |  |
| `info` | MosaicInfoOut \| null |  |  |
| `error` | string \| null |  |  |
| `created_at` | string | *required* |  |
| `updated_at` | string | *required* |  |
| `jobs` | integer | `0` | Number of simulations that used this DEM |

### MosaicInfoOut

Stitched mosaic metadata.

| Field | Type | Default | Description |
|---|---|---|---|
| `crs` | string | *required* |  |
| `bounds` | array of object | *required* |  |
| `bounds_lonlat` | array of object | *required* | (west, south, east, north) in degrees |
| `res` | array of object | *required* |  |
| `res_m` | number | *required* | Approximate pixel size [m] |
| `shape` | array of object | *required* |  |
| `nan_fraction` | number | *required* |  |
| `summit` | array of object | *required* | (lon, lat, elevation) |
| `zmin` | number | *required* |  |
| `sha256` | string | *required* |  |
| `tiles` | integer | *required* |  |
| `crs_assumed` | boolean | *required* |  |

### HealthOut

Service status.

| Field | Type | Default | Description |
|---|---|---|---|
| `status` | string | *required* |  |
| `version` | string | *required* |  |
| `commit` | string | *required* |  |
| `max_concurrent_runs` | integer | *required* |  |

