# granflow 0.1

A NumPy re-implementation of the Titan2D depth-averaged granular-flow model, with a three.js viewer.

## Run

    pip install numpy            # rasterio optional, for GeoTIFF DEMs
    python run_demo.py --out flow.json                     # ~1 min on a laptop
    python viewer/build.py viewer/template.html flow.json granflow_viewer.html

Useful flags: `--phi-bed 24 --phi-int 34 --rheology coulomb|voellmy --pressure savage-hutter|hydrostatic --pile-h 60 --pile-r 280 --n 320 --dx 30 --t-end 240 --every 2`.

## Model

- Mass + momentum, depth-averaged, on a DEM b(x, y)
- Basal Coulomb friction `h g cosθ tan φ_bed` (Titan2D default) or Voellmy (`μ`, `ξ`)
- Earth pressure coefficient k: hydrostatic, or Savage–Hutter active/passive from φ_int, φ_bed
- FV: MUSCL-minmod, hydrostatic reconstruction (Audusse 2004), Rusanov flux, SSP-RK2, CFL dt
- Friction is an implicit stopping step, so piles hold on slopes below φ_bed

Verified: lake-at-rest stays at rest (|hu| ~ 1e-12), a pile on a 10° slope with φ_bed = 20° does not move, and symmetry is preserved to machine precision. Mass is conserved to 1e-5 while the flow stays inside the domain.

## Not yet ported from Titan2D

- Adaptive mesh refinement (here: uniform grid)
- Bed-curvature (centripetal) term in the normal stress
- Internal-friction shear term (`sgn(∂u/∂y) k ∂(g h)/∂y sin φ_int`)
- Two-phase Pitman–Le model, flux (vent) sources, GIS-format output
