# 4. Erosion and entrainment

Status: planned; start after roadmap item 3 is complete.

## Goal and scope

Allow a flow to entrain a finite erodible bed with explicit mass and momentum
accounting. Select and justify a constitutive law before implementation. Begin
with entrainment only; deposition and coupled bed evolution require separate
decisions rather than implicit assumptions.

## Implementation plan

- [ ] **1. Physical specification:** review primary sources; choose the erosion
  law, units, available-bed representation, entrained material velocity and phase
  composition. Decide whether terrain elevation evolves and how this affects
  slope/curvature. Define benchmarks and tolerances.
- [ ] **2. Bed inventory:** add bounded erodible thickness/material inputs with
  validated CRS, coverage and nodata handling for any spatial inputs. Preserve
  immutable source DEMs and record bed-input hashes in provenance.
- [ ] **3. Conservative update:** transfer mass/momentum from bed inventory to
  flow, cap erosion by availability and stabilise source integration. Support
  uniform grids first, then conservative inventory transfer on adaptive meshes.
- [ ] **4. Reporting:** separate original release, entrained volume, retained mass
  and outflow. Define density-aware budgets for two-phase runs; export erosion
  fields and updated terrain if bed evolution is supported.
- [ ] **5. Application integration:** add API/YAML/CLI inputs, worker artifacts,
  Numba parity, Setup controls, result layers and captions. Regenerate API types.
- [ ] **6. Release:** verify benchmarks and regressions; document calibration
  requirements, supported model combinations and limits.

## Validation and completion criteria

Check zero-erosion equivalence, finite-bed exhaustion, nonnegative inventory,
source time-step convergence and combined bed/flow mass balance including
outflow. Test momentum transfer and phase composition against the specified law.
If terrain changes, verify geometry updates and resting-state behaviour.

Complete when erosion cannot exceed available material, budgets close within
documented tolerances, and reproducible inputs and erosion outputs work end to end.

## Required checks

Run ruff, ty, circular-import tests after module changes, targeted physical tests
and the full backend suite. Regenerate OpenAPI/types when inputs change. Use
impeccable and playwright-cli for UI changes and run the frontend build. Keep test
outputs in `backend/tests/`; append completed increments to the daily changelog.
