# 3. Internal-friction shear term

Status: planned; start after roadmap item 2 is complete.

## Goal and scope

Review and add the missing lateral/internal shear contribution where supported
by the governing model. Existing Savage–Hutter earth-pressure coefficients use
the internal friction angle; distinguish that contribution from the new term
to prevent double counting.

## Implementation plan

- [ ] **1. Derivation:** review primary equations and upstream implementation;
  document tensor components, signs, coordinate conventions, strain-rate
  regularisation, energy behaviour and applicable single/two-phase models.
  Specify benchmark tolerances and unsupported combinations.
- [ ] **2. NumPy implementation:** introduce an opt-in formulation with consistent
  reconstruction and wet/dry handling; determine its stability restriction.
- [ ] **3. Coupling:** integrate both SSP-RK2 stages, phase handling where valid,
  and adaptive patch stencils. Verify compatibility with pressure and basal friction.
- [ ] **4. Numba and configuration:** add parity, validated API/YAML/CLI settings,
  provenance and clear Setup/model-note text. Regenerate schemas and types.
- [ ] **5. Release:** document quantitative benchmark results and differences
  from the existing solver; complete regression checks.

## Validation and completion criteria

Test zero-shear cases, rotated/symmetric cases, wet/dry interfaces, resting slopes
and a controlled shearing flow. Check the derived energy behaviour, convergence,
mass conservation and NumPy/Numba agreement. Compare against the benchmark
selected in step 1; confirm disabled behaviour preserves existing results.

Complete when the derivation is reviewable, supported model combinations pass
their error budgets, and the term works through configuration and outputs.

## Required checks

Run ruff, ty, circular-import tests after module changes, targeted numerical tests
and the full backend suite before release. Regenerate OpenAPI/types as needed.
Use impeccable and playwright-cli for frontend changes and build the frontend.
Store test artifacts in `backend/tests/`; log completed increments.
