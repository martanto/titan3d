# titan3d wiki

titan3d is a Python re-implementation of the [Titan2D](https://github.com/titan2d/titan2d) depth-averaged granular-flow model. It has a FastAPI backend, a Numba solver, and a Vite/three.js web app for setting up, running and analysing simulations of volcanic mass flows on real terrain.

| Page | Read it for |
|---|---|
| **Home** (this page) | Getting started: install, prepare a DEM, first simulation |
| [Titan2D](Titan2D.md) | The model: physics, parameters, calibration, comparison with Titan2D, references |
| [Architecture](Architecture.md) | How the pieces fit: processes, data flow, storage, conventions |
| [Backend](Backend.md) | Python package: core solver, API layers, database, worker, CLI, configuration, tests |
| [Frontend](Frontend.md) | Web app: views, 3D engine, map furniture, colour maps, styling (Tailwind v4), build |
| [API Reference](API-Reference.md) | Every HTTP endpoint and schema, with examples |

Results are model output, not official hazard maps.

---

## Getting started

### 1. Install

Requirements:
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 and every backend dependency;
- [Node.js](https://nodejs.org/) 22+ to build the UI;
- a browser with WebGL 2.

It runs on Windows, Linux and macOS without GDAL or a compiler.

```bash
git clone https://github.com/martanto/titan3d.git
cd titan3d
cd frontend && npm ci && npm run build      # web UI
cd ../backend && uv sync                    # backend + Python 3.12
uv run pytest -q                            # optional: 101 tests, about 40 s
```

### 2. Prepare a DEM

You need one or more **GeoTIFF** tiles with elevation in metres.
- Tiles without a CRS are accepted when their bounds are longitude/latitude, as with Indonesian DEMNAS tiles.
- Tiles in different CRSs are warped to the first tile's CRS.
- Nodata, NaN and sentinels below −1000 m count as missing.

You can supply them in either way:
- put tiles in `dem/` at the repository root, so they become the **built-in DEM** and are stitched once on first start; or
- upload them in the app (Setup → Terrain → *Choose GeoTIFF files*). Several files at once are fine.

### 3. Start the server

```bash
cd backend
uv run titan3d serve            # http://127.0.0.1:8000  (UI + API; API docs at /api/docs)
```

For a shared server, see *Deploying behind nginx* in the README and `deploy/nginx.conf.example`.

### 4. Your first simulation (about 1 minute)

1. **Setup:** the map shows your DEM, and a pile sits at the highest point.
   - Press **Place** on *Pile 1* and click the summit or crater on the map.
   - Leave the volume at 8.5 × 10⁶ m³, or type a new one.
   - Under *Resolution and time*, choose **Quick 40 m** and set *Simulated time* to 120 s.
   - Check the **Estimate**: grid size, memory and a runtime class (it should say *seconds*).
   - Press **Run simulation**.
2. **Run:** watch the phases (domain, kernels, solving, outputs), the progress bar and the live runout and speed curves. The first run compiles the Numba kernels, which takes about 10 s.
3. **Results:** the run opens on the maximum-depth envelope in plan view.
   - Press play to watch depth or speed, and switch to **3D**.
   - Read **runout** and **H/L**, and compare H/L with tan φ_bed.
   - **Export figure** saves a PNG with its caption. The download list has the GeoTIFF, GeoJSON and KML files.

Then refine:
- lower φ_bed for longer runout;
- use **Standard 20 m** or **Fine 10 m** for detail;
- add vents;
- download the YAML config to rerun or share it.

### 5. Headless runs

```bash
cd backend
uv run titan3d init-config -o scenario.yaml     # commented template
uv run titan3d run --config scenario.yaml --dx 20
```

## FAQ

**How long does a run take?** It depends on cells × simulated time. The Semeru default (1,100 × 1,000 cells at 20 m, 300 s) takes about 85 s on a 20-thread CPU. Halving Δx multiplies the cost by about 8. The Setup estimate gives a runtime class before you run.

**Can I close the browser during a run?** Yes. Runs execute in a background process; open **Runs** later. A server restart marks running jobs *interrupted*, and **Run again** restarts them.

**Why does my flow stop so early?** The basal friction angle is too high. A Coulomb flow stops when its mobility H/L reaches about tan φ_bed. See [Titan2D → Calibration](Titan2D.md#calibration).

**Is the natural-colour terrain a satellite image?** No. It is synthesised from the DEM (elevation, slope, curvature) and labelled as such in every caption. Results default to a greyscale hillshade so colour stays reserved for data.

**Where are my outputs?** In `<project root>/data/runs/<run id>/`, alongside `backend/`, and downloadable from the Results panel. Override storage with `TITAN3D_DATA_DIR`. See [Backend → Run artifacts](Backend.md#run-artifacts) and [moving existing data](../deploy/README.md#moving-existing-data).
