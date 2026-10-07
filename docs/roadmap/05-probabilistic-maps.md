# 5. Probabilistic hazard maps from parameter sweeps

Status: planned; start after roadmap item 4 is complete.

## Goal and scope

Run reproducible ensembles and aggregate threshold exceedance on a common grid.
Distinguish an unweighted scenario frequency from a probability estimated under
specified parameter distributions and weights. Every map must state its sampling
assumptions and retain the project's unofficial model-output caption.

## Implementation plan

- [ ] **1. Ensemble specification:** define allowed varying parameters, ranges,
  units, constraints, sampling method, seed, weights, sample count and thresholds.
  Start with a deterministic explicit scenario list; add distribution sampling
  after aggregation is verified. Define statistical validation criteria.
- [ ] **2. Scheduling and persistence:** design ensemble/member records through
  repositories, migrations and existing job dispatch. Define capacity limits,
  cancellation, retries, restart recovery and member provenance.
- [ ] **3. Common-grid aggregation:** specify CRS, extent, resolution, coverage
  masks and raster alignment. Validate threshold semantics and resampling across
  adaptive runs; stream member maxima to keep memory bounded.
- [ ] **4. Failure policy:** expose completed/failed/pending counts. Label partial
  aggregates explicitly; never silently count failed or uncovered cells as
  non-exceedances. Define denominators and weight normalisation.
- [ ] **5. API and outputs:** provide ensemble submission/progress, member links,
  downloadable manifest, exceedance GeoTIFFs and summary metadata. Preserve
  seeds, weights, thresholds and code/DEM provenance.
- [ ] **6. Interface and release:** add ensemble setup, progress and maps with
  denominators, units and sampling captions. Validate convergence/uncertainty
  reporting appropriate to the sampling design and document interpretation limits.

## Validation and completion criteria

Use hand-computable tiny ensembles to verify thresholds, weights, nodata and
denominators. Test deterministic seeds, raster alignment, partial/failure policy,
retry idempotency, cancellation and restart recovery. Measure aggregation memory
and confirm existing concurrency limits apply to ensemble members.

Complete when an ensemble can be reproduced from its manifest, maps match known
aggregates, incomplete runs are explicit, and captions distinguish scenario
frequency from model-conditional probability. Outputs are not official hazard maps.

## Required checks

Run ruff, ty, circular-import tests after module changes, database/API/aggregation
tests and the full backend suite. Regenerate OpenAPI and frontend types. Apply
the security-review skill for new endpoints/user inputs; use impeccable and
playwright-cli for UI work and build the frontend. Keep test outputs in
`backend/tests/`; log every completed increment.
