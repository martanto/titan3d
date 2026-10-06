# titan3d

A Python (NumPy) re-implementation of the [Titan2D](https://github.com/titan2d/titan2d) depth-averaged granular-flow model, with a three.js viewer that plays results back in 3D.

Titan2D simulates dry granular mass flows such as block-and-ash flows, debris avalanches and rock avalanches over a digital elevation model. titan3d keeps the same governing equations and replaces the C++/AMR code with a compact NumPy solver, so models are easy to read, modify and couple to Python workflows.

The Python package is called `granflow`.

```
 DEM + pile ──► granflow.Solver ──► frames (h, |u|) ──► export.bundle ──► viewer (three.js)
                FV, NumPy           every Δt_out        zlib + base64      terrain + flow shaders
                                                        JSON (~1 MB)       timeline, probe, H/L
```

## Quick start

```bash
pip install numpy                      # rasterio is optional, for GeoTIFF DEMs
python run_demo.py --out flow.json     # synthetic volcano, ~70 s on a laptop CPU
python viewer/build.py viewer/template.html flow.json granflow_viewer.html
# open granflow_viewer.html in a browser
```

The demo releases a 7.4 × 10⁶ m³ paraboloid pile in the breached summit crater of a synthetic 1.7 km stratovolcano and runs 240 s of flow on a 320 × 320 grid at 30 m spacing.

### Demo options

| Flag | Default | Meaning |
|---|---|---|
| `--n`, `--dx` | 320, 30 | grid size and spacing (m) |
| `--t-end`, `--every` | 240, 2 | simulated time and output interval (s) |
| `--phi-bed`, `--phi-int` | 24, 34 | basal and internal friction angles (°) |
| `--rheology` | `coulomb` | `coulomb` or `voellmy` |
| `--pressure` | `savage-hutter` | earth-pressure coefficient: `savage-hutter` or `hydrostatic` |
| `--pile-h`, `--pile-r` | 60, 280 | pile height and radius (m) |
| `--out` | `flow.json` | output bundle for the viewer |

### Using the solver directly

```python
import numpy as np
from granflow import FlowParams, Solver, State, paraboloid_pile, load_dem

b, dx = load_dem("dem.tif")                      # or synthetic_volcano(...)
ny, nx = b.shape
x = (np.arange(nx) - nx / 2) * dx
y = (np.arange(ny) - ny / 2) * dx
h0 = paraboloid_pile(x, y, xc=0.0, yc=0.0, height=50.0, radius=250.0)

solver = Solver(b, dx, FlowParams(phi_bed_deg=24, phi_int_deg=34))
state = State(h0, np.zeros_like(h0), np.zeros_like(h0))
for s in solver.run(state, t_end=300, output_every=5):
    print(s.t, s.h.max())
```

## Model

Depth-averaged mass and momentum conservation on a bed `b(x, y)`:

```
h_t   + (hu)_x + (hv)_y                          = 0
(hu)_t + (hu² + ½ k g h²)_x + (huv)_y            = −g h b_x − F_x
(hv)_t + (huv)_x + (hv² + ½ k g h²)_y            = −g h b_y − F_y
```

Basal resistance `F` acts against the depth-averaged velocity:

- **Coulomb** (Titan2D default): `|F| = h g cosθ tan φ_bed`
- **Voellmy**: `|F| = h g cosθ μ + g |u|² / ξ`

The earth-pressure coefficient `k` is either 1 (hydrostatic) or the Savage–Hutter active/passive value derived from φ_int and φ_bed.

### Numerics

- Finite volume on a uniform grid
- MUSCL reconstruction with a minmod limiter
- Hydrostatic reconstruction (Audusse et al., 2004) for a well-balanced bed term with h ≥ 0
- Rusanov (local Lax–Friedrichs) interface flux
- SSP-RK2 time stepping with an adaptive CFL time step
- Friction applied as an implicit stopping step, so material comes to rest on slopes flatter than φ_bed

## Verification

| Test | Result |
|---|---|
| Lake at rest over a bump (no friction) | stays at rest, \|hu\| ≈ 1e-12 |
| Pile on a 10° slope, φ_bed = 20° | does not move |
| Symmetric pile on an inclined plane | symmetric to machine precision |
| Mass while flow stays in the domain | conserved to 1e-5 |
| Runout vs. energy line | consistent with H/L ≈ tan φ_bed |

## Viewer

`viewer/template.html` is a single-page three.js (r147) viewer. `viewer/build.py` injects a `flow.json` bundle into it.

- Terrain with hypsometric tint, hillshade and 50 m contours
- Flow coloured by depth, speed, or maximum depth reached
- Timeline scrubbing, playback rate, vertical and thin-flow exaggeration
- Hover probe for elevation, depth and speed
- Per-frame runout, mobility H/L, inundated area and mass conservation

## Repository layout

```
granflow/
  solver.py    FV solver, FlowParams, State
  terrain.py   synthetic volcano, paraboloid pile, DEM loader
  export.py    quantised, compressed JSON bundle for the viewer
run_demo.py    demo run
viewer/
  template.html  three.js viewer
  build.py       inject a bundle into the viewer
CLAUDE.md      project context for Claude Code
```

## Roadmap

Features of Titan2D not ported yet:

1. Bed-curvature (centripetal) term in the normal stress
2. Internal-friction shear term `sgn(∂u/∂y) k ∂(g h)/∂y sin φ_int`
3. Flux (vent) sources
4. GIS output: GeoTIFF of maximum depth and speed
5. Adaptive mesh refinement
6. Two-phase Pitman–Le model

Other planned work: real-DEM runs for Indonesian volcanoes, Numba or JAX acceleration, and pytest coverage of the verification cases.

## References

- Patra, A. K., et al. (2005). Parallel adaptive numerical simulation of dry avalanches over natural terrain. *Journal of Volcanology and Geothermal Research*, 139, 1–21.
- Savage, S. B., & Hutter, K. (1989). The motion of a finite mass of granular material down a rough incline. *Journal of Fluid Mechanics*, 199, 177–215.
- Audusse, E., et al. (2004). A fast and stable well-balanced scheme with hydrostatic reconstruction for shallow water flows. *SIAM Journal on Scientific Computing*, 25(6), 2050–2065.
