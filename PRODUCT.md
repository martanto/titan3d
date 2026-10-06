# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Vite + TypeScript (vanilla modules, no UI framework) in `frontend/`, three.js from npm for the 3D scene. In production the FastAPI backend serves the built frontend (`uv run titan3d serve`), so the whole app runs from one uv command with no Docker. Backend: Python 3.12, FastAPI, pydantic, SQLite job tracking, NumPy/Numba solver (`backend/`). Confirmed by the owner.

## Users

All three groups are primary (confirmed by the owner):

- **Hazard analysts at PVMBG** (Indonesia's Centre for Volcanology and Geological Hazard Mitigation; the owner is a PVMBG volcanologist). They set up block-and-ash-flow and debris-avalanche scenarios on real DEMs (Semeru first), run them at high resolution, and use the results in hazard assessments and briefings.
- **Researchers and modellers.** They compare parameters (friction angles, rheology, grid spacing, sources), check mass balance and convergence, and validate against Titan2D or field observations.
- **Public and outreach audiences.** They watch the 3D playback to understand where and how fast a flow travels. In practice this mostly happens when an analyst presents the playback (inferred).

## Product Purpose

titan3d re-implements the Titan2D depth-averaged granular-flow model in Python, with a browser app around it. A user picks or uploads a DEM, places collapse piles or vent sources, chooses material and grid parameters, and starts a run. They can follow its progress, which may take minutes to hours, then play the flow back in 3D and download GIS products. Success means a correct, reproducible simulation whose results an analyst can interpret and hand on.

## Positioning

The same physics as Titan2D: Savage–Hutter depth averaging, Coulomb or Voellmy basal friction, the bed-curvature term, flux sources. It is readable, testable Python that runs on a laptop without an HPC build, and it handles Indonesian DEMNAS tiles natively, including stitching and a missing CRS. Every run records provenance: code version, DEM hash and numerics.

## Operating Context

- Runs are long: 20 m grids over tens of square kilometres take minutes to hours. Users leave and come back, so progress must be visible and runs must survive navigation.
- Outputs move on to QGIS and Google Earth (GeoTIFF maximum depth/speed, GeoJSON/KML inundation outline). Colleagues share scenario YAML files.
- It runs on an analyst's workstation or an internal server, alone or behind basic auth.
- The built-in dataset is Semeru DEMNAS 0.27″ (≈ 8.3 m). The south-east tile of that block is missing.

## Capabilities and Constraints

- DEMs: multi-file GeoTIFF upload with server-side stitching and CRS checks; built-in Semeru; domains reprojected to local UTM.
- Sources: paraboloid piles and Titan2D-style flux (vent) sources with start, duration and initial velocity.
- Material: Coulomb or Voellmy, Savage–Hutter or hydrostatic earth pressure, curvature on/off.
- Resolution: 10–500 m (presets 40 / 20 / 10 m). A separate viewer-detail setting affects only playback.
- Outputs: 3D playback bundle, per-frame statistics (runout, H/L, area, max depth and speed, mass in domain and outflow), GeoTIFFs, GeoJSON/KML, YAML config, run log.
- Run control: queue, cancel, duplicate, delete; one run at a time by default.
- Not yet implemented: adaptive mesh refinement, two-phase (Pitman–Le) flows, the internal-friction shear term, probabilistic hazard maps.
- Results are model outputs, not official hazard maps (inferred; wording to confirm).

## Brand Commitments

- Name: **titan3d**. It credits Titan2D (Patra et al., 2005) as the model it follows.
- An incumbent viewer exists (`viewer/template.html`). No logo or other brand assets exist.

## Evidence on Hand

- Semeru DEMNAS tiles (`dem/`).
- Verification test suite (lake at rest, slope at rest, symmetry, mass balance, Numba parity) and benchmark figures in the changelog.
- No field-validation data, case studies, testimonials or institutional endorsements are on hand. Do not fabricate them.

## Product Principles

1. **Numbers you can trust.** Units on everything, visible mass balance, provenance on every run.
2. **Long runs are first-class.** Progress is honest and specific, and leaving and returning is normal.
3. **Interpretation over spectacle.** The 3D view serves reading the flow (depth, speed, reach), not decoration.
4. **GIS-native hand-off.** Every result leaves the app in formats analysts already use.
5. **Say what the model does not do.** State its limits plainly.

## Accessibility & Inclusion

WCAG 2.2 AA (inferred default). Respect reduced motion during playback and loading. English UI first; Indonesian localisation is undecided.
