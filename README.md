# titan3d

A Python re-implementation of the [Titan2D](https://github.com/titan2d/titan2d) depth-averaged granular-flow model, with a web app for setting up, running and analysing simulations on real terrain.

Titan2D simulates dry granular mass flows such as block-and-ash flows, debris avalanches and rock avalanches over a digital elevation model (DEM). titan3d keeps the same governing equations and replaces the C++ code with a compact NumPy/Numba solver behind a FastAPI service. A Vite + three.js frontend turns every run into a scientific figure: a map with graticule, scale bar, colourbar and an auto-written caption.

```
 DEM tiles ──► stitch + reproject ──► Solver (NumPy/Numba) ──► frames, maxima ──► GeoTIFF · GeoJSON · KML
 (upload)      (rasterio, UTM)        background worker       SQLite progress      3D playback + figures
```

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) and, to build the UI once, Node 22+.

```bash
cd frontend && npm ci && npm run build          # build the web UI
cd ../backend && uv sync && uv run titan3d serve # API + UI on http://127.0.0.1:8000
```

The built-in DEM is read from `dem/`; the Semeru DEMNAS tiles (0.27″ ≈ 8.3 m, from BIG) are not in the repository, so put the GeoTIFF tiles there and they are stitched on first start. Without them, upload DEM tiles in the app. Docker, running as a service and all settings are covered in [deploy/README.md](deploy/README.md).

Headless runs use the same scenario format as the web app:

```bash
cd backend
uv run titan3d init-config -o scenario.yaml      # commented default (Semeru summit collapse)
uv run titan3d run --config scenario.yaml --dx 20
```

## The web app

- **Setup**
  - Pick the built-in DEM, or upload your own GeoTIFF tiles (several files at once; they are stitched on the server).
  - Click the map to place collapse piles or vents.
  - Set the domain, material and grid spacing (presets 40 / 20 / 10 m).
  - See grid size, memory and a runtime estimate before running.
  - Download or load the scenario as YAML.
- **Running**
  - Shows real progress (simulated time, steps, ETA) through each phase, with live runout and speed curves.
  - Runs continue on the server if you close the page.
- **Results**
  - Opens on the maximum-depth envelope in plan view.
  - Playback of depth and speed in 2D or 3D, holding on the final deposit.
  - Readouts: runout, mobility H/L against tan φ_bed, area, mass balance.
  - Time-series charts, provenance, and downloads (GeoTIFF max depth/speed, GeoJSON/KML inundation outline, YAML, log).
  - Export the view as a PNG figure with its caption.
  - Presenter mode for briefings.
- **Terrain surface:** a natural-colour relief synthesised from the DEM (vegetation, bare rock, ash, incised gullies), or a greyscale hillshade.
- **Colour maps:** Crameri Scientific Colour Maps (batlow, imola, lajolla), perceptually uniform and colour-vision-deficiency friendly.

## Model

Depth-averaged mass and momentum conservation on a bed `b(x, y)`:

```
h_t   + (hu)_x + (hv)_y                          = S_h
(hu)_t + (hu² + ½ k g h²)_x + (huv)_y            = −g h b_x − F_x
(hv)_t + (huv)_x + (hv² + ½ k g h²)_y            = −g h b_y − F_y
```

- **Basal resistance:** Coulomb `|F| = h g_eff tan φ_bed` (Titan2D default) or Voellmy `|F| = h g_eff μ + g|u|²/ξ`.
- **Bed curvature:** `g_eff = cosθ (g + u·∇∇b·u)` adds the centripetal term to the normal stress.
- **Earth pressure:** `k` is 1 (hydrostatic) or the Savage–Hutter active/passive value from φ_int and φ_bed.
- **Sources:** paraboloid piles at t = 0, and Titan2D-style flux (vent) sources with start time, duration and initial velocity.

### Numerics

- Finite volumes on a uniform UTM grid; MUSCL reconstruction (minmod) of depth, bed and velocity.
- Hydrostatic reconstruction (Audusse et al., 2004) for a well-balanced bed term with h ≥ 0. Depth and bed are reconstructed separately so thin flows cannot be trapped on steep slopes.
- Rusanov flux; SSP-RK2 with an adaptive CFL time step; implicit friction stopping step.
- **Active window:** only the bounding box of cells holding material is computed. This is exact, because dry cells produce no flux.
- **Backends:** Numba (default, parallel) or NumPy (reference); float64 or float32.
- **Outflow accounting:** in-domain volume plus outflow equals released volume.

Performance: the default Semeru domain (22 × 20 km at 20 m, 1,100 × 1,000 cells) simulates 300 s in about 85 s on a 20-thread laptop CPU.

## Verification

`uv run pytest` in `backend/` (95 tests) covers:

| Test | Result |
|---|---|
| Lake at rest over a bump | stays at rest, \|hu\| < 1e-10 |
| Pile on a 10° slope, φ_bed = 20° | does not move |
| Symmetric pile on an inclined plane | symmetric to 1e-10 |
| Mass balance with outflow | in-domain + outflow = released, 1e-5 |
| Active window vs full domain | bit-identical |
| Numba vs NumPy | agree to 1e-10 |
| Curvature on plane / cylinder | 0 / g + u²/R |
| Flux source volume and timing | exact to 1e-12 |
| DEM stitching, CRS handling, coverage checks | synthetic tiles (real Semeru opt-in) |
| API end to end (upload → run in a worker → downloads) | real worker processes |

## Repository layout

```
backend/                FastAPI service and solver (uv project)
  src/titan3d/core/     solver, numerics, rheology, curvature, sources, DEM, scenario, export (no web deps)
  src/titan3d/api/      routes → controllers → core; schemas; background worker and dispatcher
  src/titan3d/db/       SQLite job and DEM tracking
  openapi.json          API schema (checked by tests)
frontend/               Vite + TypeScript + three.js web app
dem/                    built-in DEM tiles (local only, git-ignored)
deploy/                 how to run (uv, service, optional Docker)
docs/                   plan and design reviews
```

## Roadmap

Not yet ported from Titan2D:
- adaptive mesh refinement;
- two-phase (Pitman–Le) flows;
- the internal-friction shear term;
- erosion and entrainment;
- probabilistic hazard maps from parameter sweeps.

## References

- Patra, A. K., et al. (2005). Parallel adaptive numerical simulation of dry avalanches over natural terrain. *Journal of Volcanology and Geothermal Research*, 139, 1–21.
- Savage, S. B., & Hutter, K. (1989). The motion of a finite mass of granular material down a rough incline. *Journal of Fluid Mechanics*, 199, 177–215.
- Audusse, E., et al. (2004). A fast and stable well-balanced scheme with hydrostatic reconstruction for shallow water flows. *SIAM Journal on Scientific Computing*, 25(6), 2050–2065.
- Delestre, O., et al. (2012). On the use of the hydrostatic reconstruction for flows on a slope. *International Journal for Numerical Methods in Fluids*, 72, 269–300.
- Crameri, F., Shephard, G. E., & Heron, P. J. (2020). The misuse of colour in science communication. *Nature Communications*, 11, 5444.
- DEMNAS: Badan Informasi Geospasial (BIG), Indonesia.
