# 1. Adaptive mesh refinement

Status: planned; first roadmap item to implement.

AMR means **Adaptive Mesh Refinement**: changing computational cell sizes where
detail is needed. See [Terminology](../../wiki/Terminology.md#mesh-and-resolution)
for its distinction from active windows, adaptive time steps and numerical order.

## Goal and scope

Resolve flow fronts and changing depth with finer cells while reducing work in
smooth or dry regions. The current active window reduces the area evaluated on
a uniform grid; it does not change cell size. Retain that solver as the reference
and default until the adaptive solver passes verification.

Initial proposal: rectangular patches with a 2:1 refinement ratio, one additional
level and a shared time step. Confirm this design during step 1. Multiple levels,
time subcycling and distributed execution belong to later increments.

## Implementation plan

- [ ] **1. Numerical design:** inspect the uniform-grid assumptions in `core/grid.py`,
  `solver.py`, `numerics.py`, `curvature.py`, `sources.py`, `scenario.py` and
  `export.py`. Review the upstream AMR implementation and primary numerical
  references. Record patch ownership, ghost exchange, refinement indicators,
  regridding frequency, positivity, well balancing and conservation tolerances
  in a design note before implementation.
- [ ] **2. Mesh infrastructure:** introduce patch metadata and conservative
  restriction/prolongation of depth and momentum. Define terrain sampling and
  source integration on each level; avoid counting overlapping cells twice.
- [ ] **3. Reference stepping:** implement NumPy patch stepping, ghost exchange,
  a CFL limit covering all levels, and coarse/fine flux correction compatible
  with both SSP-RK2 stages. Test a fixed refined patch before dynamic regridding.
- [ ] **4. Adaptation:** refine around sources and flow fronts, buffer patches for
  the reconstruction stencil, and coarsen with hysteresis. Account for volume,
  outflow and maxima when patches appear or disappear.
- [ ] **5. Outputs and configuration:** define the regular output raster and
  conservative resampling rules, distinguishing solver resolution from viewer
  detail. Add validated opt-in settings through `ScenarioRequest`, YAML and CLI;
  record refinement settings in provenance. Preserve existing uniform runs.
- [ ] **6. Acceleration and interface:** add Numba parity, then expose the verified
  settings and resolution information in Setup and Results. Regenerate OpenAPI
  and frontend types when the schema changes.
- [ ] **7. Verification and release:** compare against uniform fine-grid runs,
  publish accuracy/runtime/memory measurements, document limitations and
  complete the project checks.

## Validation and completion criteria

Pass lake-at-rest, slope-at-rest, wet/dry front, symmetry and mass balance tests
across patch boundaries and regridding. Check pile and vent volume integration,
outflow, NumPy/Numba parity and output georeferencing. Set explicit error budgets
for depth, runout and inundated area in step 1; measure against uniform fine-grid
references on synthetic terrain and a reproducible DEM case. Benchmark after
kernel warm-up at comparable accuracy, including patch-management costs.

Complete when opt-in AMR works end to end, conservation and error budgets pass,
existing uniform-grid tests pass, and measured costs and limits are documented.
Do not claim a speedup before measurement.

## Required checks

For backend module changes: ruff, `uvx ty check src/`,
`uv run pytest tests/test_imports.py -v`, targeted numerical tests and the full
backend suite before release. Keep generated test artifacts under `backend/tests/`.
For frontend changes: impeccable and playwright-cli skills, build, and desktop/mobile
checks in light/dark themes. Append each completed increment to the daily changelog.
