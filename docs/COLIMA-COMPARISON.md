# Colima solver comparison

This is the historical uniform-grid comparison. The subsequent
[AMR verification report](AMR-VERIFICATION.md) repeats the original Titan2D run
and compares experimental titan3d AMR with the unchanged uniform 5 m solver,
including new figures, numerical checks and measured runtime/memory costs.

## Reading the terminology

**AMR (Adaptive Mesh Refinement)** changes cell sizes during a simulation:
smaller cells resolve fronts and other changing features, while larger cells
reduce work elsewhere. Titan2D used AMR in this comparison, with a smallest saved
cell size of about **3.533 m**. titan3d used separate uniform **10, 5 and 2.5 m**
grids. Its active window changes the region evaluated, not the cell size.

**First order / second order** describe the numerical method's expected error
scaling, separately from mesh spacing. The selected Titan2D run is first order;
titan3d uses MUSCL reconstruction and SSP-RK2 time integration. Limiters and sharp
flow fronts can reduce the achieved order, so a second-order label alone does
not establish closer agreement. An adaptive CFL time step changes time-step
length; it does not make a fixed grid adaptive.

The [wiki terminology page](../wiki/Terminology.md) also defines DEM, UTM, CFL,
MUSCL, SSP-RK2, leaf cells, sampled envelopes, runout, IoU, MAE, RMSE and mass
balance. See [output and comparison metrics](../wiki/Terminology.md#outputs-and-comparison-metrics)
when interpreting the figures and screening results.

## Plan

- [x] Create `dev/colima-solver-comparison`.
- [x] Inspect the upstream Colima case and identify release-shape differences.
- [x] Confirm Docker availability and download the official Titan2D 4.2.0 binary.
- [x] Establish a reproducible Linux container runtime and record binary/DEM hashes.
- [x] Run Titan2D on the Colima DEM for 150 s, with saved states at shared times.
- [x] Run titan3d with matched cylinder geometry and material inputs at 5 m;
  include a coarser resolution check and explicitly document remaining model differences.
- [x] Extract adaptive-cell state statistics, conservatively rasterise depth on
  a common UTM grid, and compare footprints and depth errors.
- [x] Produce maximum-depth/difference maps and speed/runout/volume time series.
- [x] Test extraction and metrics on known synthetic data; publish results and limitations.

## Comparison contract

Use the Colima EPSG:32613 DEM, release centre (644956, 2157970) m,
cylinder radius 55 m and height 30 m, zero initial velocity, Coulomb basal/internal
friction 27°/37°, and a shared 150 s window. Preserve the upstream first-order AMR
scheme and titan3d's second-order fixed-grid scheme rather than interpreting them
as identical solvers. Record differences in gravity, stress and terrain treatment.

Compute volume directly from saved cell depth times cell area, separate from any
Titan2D log diagnostic. Report both analytic release volume and each solver's
discrete initial volume; report outflow separately where available. Use h > 0.1 m
for front distance, area and speed summaries. Maximum-depth comparisons must
state whether maxima cover every step or only shared saved times. Exclude no-data
cells from metrics and distinguish dry zero-depth from missing coverage.

Keep raw downloads, runtime files and generated artifacts under
`backend/tests/out_colima_comparison/` (git-ignored). Commit scripts, tests and
the report, without committing the DEM or the Titan2D distribution. Define any
acceptance thresholds before evaluating results; similarity is an empirical
finding, not an assumption or evidence of field validation.

Exploratory screening criteria recorded before extracting comparative metrics:
final front distance within 10%, peak saved-state speed within 20%, maximum-depth
footprint intersection-over-union at least 0.70, and titan3d in-domain plus outflow
mass balance within 0.1% of its discrete initial volume. Depth MAE, RMSE and bias
are reported without a pass threshold; one benchmark cannot establish general
solver equivalence. Report failing checks without fitting parameters to pass.

Sources: [official release](https://github.com/TITAN2D/titan2d/releases/tag/v4.2.0),
[upstream Colima input](https://github.com/TITAN2D/titan2d/blob/b86f17412fe4dd180c2125eabd85bf6554328a79/share/titan2d_examples/colimafinemini/Coulomb_GeoTIFF/input.py).

## Results — 2026-10-07

Titan2D 4.2.0 was executed successfully in Docker Desktop's Linux engine.
The comparison used the production titan3d solver, with a cylinder initialised
only in the test harness. No production physics, friction values or parameters
were fitted to the reference results. All four runs reached 150 s.

The 5 m run reproduces the general flow paths and final front distance closely,
but does **not** pass all similarity screening criteria. The maximum-depth
footprint overlaps by 68.09%, below the specified 70%; final deposit overlap is
only 39.01%. Close runout alone does not establish numerical equivalence.
Across all shared times, the 5 m front-distance RMSE is 80.16 m and speed RMSE
is 5.55 m/s. Its maximum mass-budget residual is 2.22 × 10⁻¹⁶ of initial volume.

| Metric | Titan2D AMR | titan3d 10 m | titan3d 5 m | titan3d 2.5 m |
|---|---:|---:|---:|---:|
| Final front distance [m] | 2287.24 | 2690.29 | 2267.54 | 2150.22 |
| Front distance difference | — | +17.62% | −0.86% | −5.99% |
| Peak speed in shared saved states [m/s] | 53.18 | 76.15 | 60.61 | 57.82 |
| Peak speed difference | — | +43.18% | +13.96% | +8.71% |
| Maximum-depth footprint IoU | — | 57.72% | 68.09% | 64.45% |
| Maximum-depth RMSE, wet union [m] | — | 0.889 | 0.768 | 0.727 |
| Final-depth footprint IoU | — | 6.30% | 39.01% | 32.68% |
| Final-depth RMSE, wet union [m] | — | 1.019 | 0.915 | 0.879 |
| Initial volume / analytic cylinder | 99.84154% | 100.00208% | 100.00105% | 100.00131% |

For the primary 5 m comparison, final runout, peak speed and titan3d mass balance
pass their screening criteria; the maximum-depth footprint criterion fails.
`colima_report.py --check` therefore intentionally exits with status 1 after
writing the artifacts. This is a measured scientific mismatch, distinct from a
failure of the harness unit tests.

The native DEM resolution is 5 m. The 2.5 m run interpolates that terrain rather
than adding new topographic information. Changing titan3d from 5 m to 2.5 m
changes final front distance by about 5.2%, and changing 10 m to 5 m changes it by
about 15.7%. This is resolution sensitivity, not a formal convergence proof.
Refinement reduces peak-speed and depth-RMSE differences without monotonically
improving footprint overlap. A single Colima run cannot validate all terrain,
friction laws or source types.

Titan2D completed 5611 steps with four OpenMP threads and a minimum saved leaf
cell size of about 3.533 m. titan3d used eight Numba threads and completed
1363 / 2547 / 5235 steps at 10 / 5 / 2.5 m. Measured titan3d run times, including
saved-state writing, were 11.0 / 80.1 / 428.1 s; the Titan2D log reports 168.79 s.
These are different execution environments and output workloads, so these
numbers are not a controlled performance comparison.

## Accounting and remaining differences

- The analytic cylinder volume is 285099.533 m³. The harness integrates its edge
  cells with 32 × 32 midpoint quadrature; it does not renormalise the release to
  conceal discretisation error. Titan2D uses its own cylinder integration.
- Titan2D's directly integrated saved-state volume ends at 99.90433% of its own
  initial volume: a 0.09567% drift. Its `stat volume` log diagnostic falls to
  roughly 95% of the analytic volume, which is different from total saved-state
  volume. The dashed curve is labelled separately. It must not be presented as
  the solver's mass loss. titan3d retains its discrete initial volume to
  floating-point precision, with no measured outflow in these runs.
- Front, speed and area use h > 0.1 m. For Titan2D, speed is momentum/depth on
  native adaptive cells; front distance uses their centres. titan3d uses the same
  definitions on native uniform cells. Speed is not interpolated from a raster.
- Depth maps use a common 5 m UTM grid. Adaptive depth is transferred by exact
  rectangular overlap, preserving the saved-state volume. The 2.5 m states are
  area-averaged before taking the temporal maximum. Dry cells are zero; all DEM
  cells must have valid elevation. Conservation is checked at every reference
  output, and the extractor rejects invalid field lengths or cell geometry.
- Both maximum-depth maps include the release footprint and use only shared
  states at 0, 1, …, 150 s. They are sampled envelopes, not every-step maxima.
  Titan2D's extra iteration-triggered states are excluded. Colourbar triangles
  indicate saturation: the depth upper limit is the pooled wet-cell 99.5th
  percentile; the symmetric difference limit is its absolute 99th percentile.
  The complete values remain in the NPZ files and quantitative metrics.
- Schemes differ: Titan2D uses first-order AMR; titan3d uses fixed-grid MUSCL and
  SSP-RK2. DEM sampling, stress terms and stopping treatment are not established
  as equivalent. titan3d retains its Savage–Hutter pressure and curvature
  defaults; its missing internal-friction shear term remains on the roadmap.
  Gravity is 9.8 m/s² in the upstream configuration and 9.81 m/s² in titan3d;
  dry-depth handling also differs. These effects have not been isolated here.
- The web-app example in `COLIMA.md` remains a 10 m **paraboloid adaptation**.
  This benchmark bypasses that source shape in the test harness. The benchmark
  results do not establish parity for the web-app example.

## Comparison figures

These published figures and data are attached to
[PR #7's comparison comment](https://github.com/martanto/titan3d/pull/7#issuecomment-6039454974)
and can be viewed with GitHub access to the repository, without running the
harness locally.

### Maximum flow depth and difference

![Colima maximum-depth comparison: Titan2D AMR, titan3d at 5 m, and titan3d minus Titan2D, with 0.1 m footprint outlines](https://github.com/user-attachments/assets/d86463a0-180d-436d-a102-9252860f5651)

Shared saved states over 0–150 s, shown on the same terrain and UTM grid.
Black outlines show the Titan2D footprint; orange outlines in the difference
panel show titan3d. [Download the depth figure as PDF](https://github.com/user-attachments/files/33159715/maximum-depth.pdf).

### Speed, front distance and volume

![Colima time-series comparison: maximum speed, front distance and volume for Titan2D and titan3d at 10, 5 and 2.5 m, with the separate Titan2D log volume diagnostic](https://github.com/user-attachments/assets/154b3ede-d791-4da5-9c69-18847525c25d)

The speed and front-distance curves use h > 0.1 m at shared saved times. Solid
volume curves integrate saved states; the dotted Titan2D curve is its separate
log diagnostic. [Download the time-series figure as PDF](https://github.com/user-attachments/files/33159729/time-series.pdf).

Published data accompanying the figures:

- [Metrics and screening verdicts (JSON)](https://github.com/user-attachments/files/33159724/metrics.json)
- [Run environment and provenance (JSON)](https://github.com/user-attachments/files/33159726/provenance.json)
- [Shared-state time series (CSV)](https://github.com/user-attachments/files/33159727/time_series.csv)

The footprint screening criterion still fails as reported above; these figures
illustrate the measured agreement and differences.

## Local artifacts

Harness-generated artifacts remain local and git-ignored. The following local
links work after running the harness in this checkout; published copies are
linked above:

- [Maximum-depth and difference figure](../backend/tests/out_colima_comparison/maximum-depth.png)
- [Speed, front distance and volume figure](../backend/tests/out_colima_comparison/time-series.png)
- [PDF depth figure](../backend/tests/out_colima_comparison/maximum-depth.pdf)
- [PDF time-series figure](../backend/tests/out_colima_comparison/time-series.pdf)
- [Metrics and screening verdicts](../backend/tests/out_colima_comparison/metrics.json)
- [Shared-state CSV](../backend/tests/out_colima_comparison/time_series.csv)
- [Run environment](../backend/tests/out_colima_comparison/provenance.json)

Raw Titan2D XDMF/HDF5 and logs are in `titan2d/`; titan3d frames and manifests are
in `titan3d-10m/`, `titan3d-5m/` and `titan3d-2.5m/` under the same output folder.
The report adds plotting versions and hashes; initial run manifests were written
before extra environment fields were added to the harness, so the environment
was recorded afterward in `provenance.json`. Core code remained unchanged.

## Reproduce on Windows with Docker Desktop

Prerequisites: running Linux Docker engine, backend environment installed with
`uv sync`, and `dem/colimafinemini.tif` from the documented upstream example.
Run the preparation commands from the repository root in PowerShell:

```powershell
$comparisonRoot = Join-Path $PWD 'backend/tests/out_colima_comparison'
New-Item -ItemType Directory -Force "$comparisonRoot/toolchain", "$comparisonRoot/titan2d" | Out-Null
Invoke-WebRequest 'https://github.com/TITAN2D/titan2d/releases/download/v4.2.0/titan2d-v4.2.0-Linux-64bit.tar.gz' -OutFile "$comparisonRoot/toolchain/titan2d-v4.2.0-Linux-64bit.tar.gz"
Get-FileHash "$comparisonRoot/toolchain/titan2d-v4.2.0-Linux-64bit.tar.gz" -Algorithm SHA256
docker run --rm --mount "type=bind,source=$comparisonRoot,target=/work" ubuntu:18.04 bash -c 'tar -xzf /work/toolchain/titan2d-v4.2.0-Linux-64bit.tar.gz -C /work/toolchain'
docker build -t titan3d-colima-titan2d:4.2.0 -f backend/tests/colima_runtime.Dockerfile backend/tests
Copy-Item backend/tests/colima_titan2d.py "$comparisonRoot/titan2d/input.py"
$comparisonDem = Join-Path $PWD 'dem'
docker run --rm --mount "type=bind,source=$comparisonRoot,target=/work" --mount "type=bind,source=$comparisonDem,target=/dem,readonly" -w /work/titan2d titan3d-colima-titan2d:4.2.0 bash -c '/work/toolchain/titan2d-v4.2.0/bin/titan -nt 4 input.py > run.log 2>&1'
```

The archive SHA-256 for this run was
`4d173502994dc745eaa9392f1e914175fd4a7f0b8b01c3e3fa1ad677e167befc`;
the DEM SHA-256 was
`fb5086ce180ad2715c78f6b4d746c9327946cd42ec5ad8961024e6d0e54bdb11`.
The runtime Dockerfile pins the base-image digest; the portable Titan2D package
supplies its Python 2.7, GDAL and HDF5 libraries, with OpenMP supplied by the
container. No host Python 2 installation is needed.

Then, from `backend/`:

```powershell
uv run --no-sync python tests/colima_comparison.py --dx 10
uv run --no-sync python tests/colima_comparison.py --dx 5
uv run --no-sync python tests/colima_comparison.py --dx 2.5
uv run --no-sync --with h5py --with seaborn --with matplotlib python tests/colima_report.py --check
uv run --no-sync --with h5py --with seaborn --with matplotlib pytest tests/test_colima_comparison.py -q
uv run --no-sync pytest -q
```

`--no-sync` uses the already installed backend environment and avoids replacing
the Windows CLI executable while the app server is running. The plotting/HDF5
packages are isolated extra dependencies, not additions to the production
backend. Each model run writes fresh artifacts into its own output directory;
retain earlier results separately before replaying. Wait for Titan2D to finish
before extracting its XDMF. `--reuse-reference` is optional for regenerating
plots from an already extracted, unchanged reference run; omit it after rerunning
Titan2D. `--check` reports a failed screening criterion with a nonzero exit code
but still writes the plots and metrics.

## Verification and next work

Ten synthetic harness tests passed with HDF5 dependencies available: conservative
transfer, clipping/dry cells, wet-union errors, three-resolution cylinder volume,
invalid depths and XDMF geometry/momentum extraction. The regular backend suite
passed 113 tests, with the real-DEM opt-in and optional HDF5 test skipped. The
HDF5 test was run separately and passed. All 46 circular-import checks, ruff,
formatting and backend ty checks passed. Pytest's output-directory exclusion
prevents collecting the downloaded external Python 2 runtime.

Next isolate differences using controlled gravity/terrain/stress experiments,
then add planar analytic cases, other friction settings and Voellmy comparisons.
Do not adjust physical parameters solely to match this footprint. These figures
compare model outputs and are not official hazard maps or field validation.
