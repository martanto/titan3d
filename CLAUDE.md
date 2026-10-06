# granflow — project context

Python (NumPy) re-implementation of the Titan2D depth-averaged granular-flow model
(https://github.com/titan2d/titan2d), with a three.js 3D playback viewer.
Owner: Anto (PVMBG volcanologist). Work incrementally with small, targeted changes.

## Layout
- `granflow/solver.py`  — FV solver: MUSCL-minmod, hydrostatic reconstruction (Audusse 2004),
  Rusanov flux, SSP-RK2, adaptive CFL dt; Coulomb or Voellmy basal friction applied as an
  implicit stopping step; earth-pressure k hydrostatic or Savage–Hutter act/pass.
- `granflow/terrain.py` — synthetic breached stratovolcano, paraboloid pile, `load_dem` (GeoTIFF via rasterio, or .npy)
- `granflow/export.py`  — quantise h (sqrt, uint8), |u| (uint8), terrain (uint16); zlib + base64 JSON bundle
- `run_demo.py`         — demo run (defaults: 320×320 @ 30 m, φ_bed 24°, φ_int 34°, pile H 60 m R 280 m, 240 s, frame every 2 s)
- `viewer/template.html` + `viewer/build.py` — three.js r147 (UMD) + pako viewer; build injects flow.json at `/*__DATA__*/null`

## Conventions
- Arrays are [j, i] = [y, x]; y increases with j (north = +y). In three.js: X = x/1000, Y = (b - zmin)·vex/1000, Z = -y/1000 (km units).
- Stats per frame: t, vol (fraction of initial), hmax, umax, area (km², h > 0.1 m), runout (m from pile centre).

## Verified
- Lake at rest stays at rest (|hu| ~ 1e-12); pile on 10° slope with φ_bed 20° stays put; symmetry to machine precision.
- Mass conserved to 1e-5 while flow stays in domain. φ_bed 16° on the demo cone runs off the 9.6 km domain (consistent with H/L ≈ tan φ_bed).
- Demo run takes ~70 s on CPU.

## Not yet ported from Titan2D (candidate next steps)
1. Real DEM run (Lewotobi Laki-laki / Merapi) via `load_dem`
2. Bed-curvature (centripetal) term in the normal stress
3. Internal-friction shear term `sgn(∂u/∂y) k ∂(g h)/∂y sin φ_int`
4. Flux (vent) sources; GIS output (GeoTIFF of max depth / max speed)
5. Performance (Numba or JAX); adaptive mesh refinement; two-phase Pitman–Le
6. Unit tests for the verification cases above (pytest)
