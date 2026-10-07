# 2. Two-phase (Pitman–Le) flows

Status: planned; start after roadmap item 1 is complete.

## Goal and scope

Add an explicit solid/fluid model alongside the existing single-phase solver.
The governing equations, closures and numerical method require a documented
review of primary sources before coding. A rheology switch alone is insufficient.

## Implementation plan

- [ ] **1. Model specification:** review Pitman–Le equations and upstream code;
  document state variables, units, densities, phase fractions, pressure closures,
  drag, boundary conditions and supported physical limits. Choose benchmarks
  and error budgets before implementation.
- [ ] **2. State and inputs:** define separate phase mass and momentum, validated
  material/source inputs and an explicit model selector. Preserve single-phase
  configuration compatibility and include model identity in provenance.
- [ ] **3. Reference solver:** implement NumPy fluxes, sources, wave-speed bounds
  and stable drag coupling. Handle dry cells and vanishing phase fractions;
  verify on a uniform grid before integrating with AMR.
- [ ] **4. Integration:** extend workers, phase-specific statistics and exports.
  Define conservative transfer for each phase on the adaptive mesh and test it.
- [ ] **5. Acceleration and UI:** add Numba parity, regenerate API types, and
  expose phase-specific parameters, legends, units and model notes.
- [ ] **6. Release:** document benchmark results, valid parameter ranges and
  limitations; complete numerical and application regression checks.

## Validation and completion criteria

Check separate phase mass balances including sources/outflow, bounded fractions,
nonnegative depths, drag momentum exchange and time-step convergence. Verify
analytical or published benchmark cases and only those single-phase limits
supported by the chosen equations. Test uniform/adaptive and NumPy/Numba parity.

Complete when the documented model passes its benchmark error budgets, phase
outputs work end to end, and existing single-phase scenarios remain valid.

## Required checks

Run ruff, ty, circular-import tests after module changes, targeted physics tests
and the full backend suite before release. Regenerate OpenAPI/types for API
changes. Use impeccable and playwright-cli for UI changes and run the frontend
build. Keep test outputs in `backend/tests/`; log every completed increment.
