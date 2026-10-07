# Adaptive mesh refinement: verification and Colima comparison

Verified on 2026-10-07/08 on `ft/adaptive-mesh-refinement`. This completes the
first, **experimental** AMR increment: one 2:1 refinement level and a shared
time step. The uniform solver remains the default. The numerical contract and
predeclared budgets are in [AMR-DESIGN.md](AMR-DESIGN.md).

## What passed, and what did not

AMR passes all five predeclared Colima budgets **against the unchanged uniform
fine-grid solver**. Maximum-depth footprint IoU is 97.19%, wet-union depth RMSE
is 0.106 m, final runout differs by +0.068%, peak saved speed by +0.306%, and the
largest every-step mass-budget residual is 4.08 × 10⁻¹⁶ of initial volume.

AMR does **not** establish Titan2D equivalence. Against original Titan2D 4.2.0,
maximum-depth footprint IoU is 67.99%, below the existing 70% screening threshold.
Runout and peak-speed screening pass. The uniform solver also fails that
footprint check (68.09%). Introducing mesh adaptation does not remove the
remaining physics, terrain and scheme differences documented in
[COLIMA-COMPARISON.md](COLIMA-COMPARISON.md).

The initial implementation is **slower and uses more process memory** than the
uniform active-window solver. It retains dense finest-grid terrain, ownership,
state/output and maximum arrays; it rebuilds a leaf-face graph and transfers
between leaves and raster states. Fewer leaves do not imply a speedup.

## Mathematical checks

The following 27 numerical tests and two CLI tests pass:

| Property | Independent check |
|---|---|
| Ownership and geometry | Sum leaf areas equals the unchanged domain area; each leaf side has its full width in face segments; odd-sized domain edges remain covered exactly |
| Restriction/prolongation | Four-child means preserve depth and both momenta; an independently calculable partially dry water-fill case gives depths `[0.4, 0, 0, 0]` |
| Shared face conservation | Area-integrated mass RHS plus signed boundary flux cancels; compact flat-bed flow has zero area-integrated momentum RHS, including nonzero coarse/fine exchanges |
| Hydrostatic resting lake | Momentum and free-surface errors remain below 1e-9 across mixed cells and repeated split/merge operations, with hydrostatic pressure |
| Gravity sign and units | Uniform depth on a planar bed satisfies the independent PDE result `q_x,t = -g h b_x`, including the mixed-size interface |
| Wet/dry dynamics | Frictionless dry-bed dam break agrees with the analytic Ritter depth solution; positive finite depth, mixed-interface transport and outflow are exercised |
| Positivity | Donor draining bounds outgoing volume even in an oversized Euler stage, preserving mass; production stepping uses a CFL bound |
| CFL | A prescribed two-component velocity verifies the sum of both directional wave speeds and the finest leaf width |
| Friction stopping | A pile on a 10° slope with 20° basal friction stays within 1 m of its initial centre and below 0.5 m/s |
| Dynamic accuracy/symmetry | Symmetric moving pile remains symmetric; fine-grid RMSE, runout and area budgets pass |
| Sources | Delayed vent starts at the declared time; exact active-interval integration reproduces the fixed finest-grid discrete source volume; vent cells remain refined |
| Regridding/maxima | Coarsening waits three quiet updates; historical maxima survive refinement removal |
| Precision | Float64 and float32 close in-domain plus outflow mass budgets at the specified 1e-8 / 1e-5 tolerances |
| NumPy/Numba | Both Coulomb/Voellmy laws and hydrostatic/Savage–Hutter pressure agree within 1e-10 on nonflat terrain with curvature |
| Uniform reference | Fully refined spatial RHS matches the uniform MUSCL calculation; matching time steps reproduce its RK stages to 1e-12 on nonflat terrain for both pressure models |
| CLI | `--amr` and `--no-amr` override YAML through the validated scenario schema |

The API suite also verifies YAML round-trip, validation rejection, an actual
spawned AMR worker, run provenance, viewer bundle and GeoTIFF resolution, shape
and CRS. The complete backend suite passes **149 tests**, with the existing
real-DEM opt-in and optional HDF5 test skipped in the normal environment.
All **10 HDF5 comparison tests** pass separately with their optional dependencies.
All **48 circular-import checks** pass. Ruff, backend `ty`, OpenAPI freshness,
frontend type generation and production build pass. Edge checks cover Setup and
completed AMR Results on desktop/mobile in light/dark themes, retained keyboard
focus on the AMR toggle, and no horizontal overflow in Setup. The browser console
has no errors or warnings, and the impeccable detector reports no findings.

The lake guarantee is for constant hydrostatic pressure and a fully wet free
surface. It does not prove equilibrium for variable Savage–Hutter pressure or
preservation of unresolved partially dry shoreline geometry. Formal convergence
order at changing mixed-size interfaces is not established by these tests.

## Colima contract and measurements

Use the same EPSG:32613 DEM and complete 4,500 × 4,500 m domain, release centre
(644956, 2157970) m, cylinder radius 55 m and height 30 m, Coulomb basal/internal
friction 27°/37°, zero initial speed and shared saved states at 0, 1, …, 150 s.
The source cylinder is integrated by the existing comparison harness; the
production web example remains a paraboloid adaptation.

Run original Titan2D again in the existing pinned Docker runtime, using its
official 4.2.0 portable binary, first-order AMR and four OpenMP threads. Run
titan3d uniform 5 m and AMR 5–10 m with the same material parameters, default
curvature/Savage–Hutter treatment, float64 and eight Numba threads. No friction,
gravity, thresholds or other physical inputs are fitted to the reference.

AMR defaults are gradient trigger 0.05, two parent-cell buffer, regrid every four
complete RK steps and three quiet updates before coarsening. Outputs remain
900 × 900 cells at 5 m. API/UI configurations retain their 10 m minimum finest
spacing; the 5 m benchmark invokes the computation core directly.

| Metric | Titan2D | Uniform 5 m | AMR 5–10 m |
|---|---:|---:|---:|
| Final front distance [m] | 2287.242 | 2267.536 | 2269.068 |
| Peak saved-state speed [m/s] | 53.184 | 60.607 | 60.793 |
| Maximum-depth IoU vs Titan2D | — | 68.09% | 67.99% |
| Maximum-depth wet-union RMSE vs Titan2D [m] | — | 0.768 | 0.783 |
| Final-depth IoU vs Titan2D | — | 39.01% | 38.74% |
| Direct saved-state volume drift | −0.09567% | roundoff | roundoff |
| Steps | 5611 | 2547 | 4164 |
| Computational leaf cells at saved times | adaptive | 810000 | 203304–299064 |
| Mesh changes | upstream controller | 0 | 1042 |
| Observed run time [s] | 215.4 (upstream log) | 106.9 | 1945.9 |
| Separate kernel warm-up [s] | — | 2.304 | 0.213 |
| Sampled whole-process peak RSS [MB] | not measured comparably | 283.7 | 389.1 |

AMR versus uniform: maximum-depth IoU **97.19%**, depth RMSE **0.106 m**,
final-depth IoU **96.40%**, final-depth RMSE **0.196 m**. Maximum-depth inundated
area changes from 1.723675 to 1.685875 km² (−2.19%). The analytic cylinder
volume is 285099.533 m³; both titan3d runs start at 285102.539 m³, without
renormalisation. Their largest mass residual is checked at every step, rather
than only at outputs.

The observed AMR time is about 18.2 times the uniform time. These are workstation
measurements, including mesh creation/management, source/maxima accounting and
compressed saved-state output. Some verification/reference workloads overlapped,
so they are not a controlled performance benchmark. RSS samples include the
Python process, terrain and retained outputs; they are not just leaf-state
storage. Repeated isolated timing and memory studies are needed before
performance claims. Numba accelerates neighbour derivatives and face
accumulation; mesh construction, transfers and other vectorised work remain
NumPy. The AMR CFL bound sums directional speeds; the uniform solver uses its
existing bound, explaining part of the step-count difference.

## Figures and data

Artifacts below are local, git-ignored test outputs. Reproduction creates them;
they are not bundled with the source checkout.

![Titan2D, uniform and AMR maximum-depth maps and AMR minus Titan2D difference](../backend/tests/out_amr/maximum-depth.png)

Maximum-depth maps include the release and use only shared saved times. Black
outlines are Titan2D at 0.1 m; orange outlines are titan3d AMR. All depth panels
share one scale. Colourbar extensions indicate saturation; metrics use complete
values. Coordinates are UTM 13N metres.

![Colima speed, front-distance and integrated-volume time series](../backend/tests/out_amr/time-series.png)

Speed and front distance use h > 0.1 m. Reference statistics use native Titan2D
leaves; AMR reports native leaf statistics separately from output-raster
statistics in its saved JSON. Upstream screening uses native AMR statistics;
fine-grid fidelity uses the common raster statistics. In this run the reported
peak speed and final front distance agree between those AMR representations.
The dotted Titan2D log volume diagnostic is separate from integrated saved-state
volume and must not be interpreted as its total mass loss.

![AMR leaf counts and observed titan3d run times](../backend/tests/out_amr/mesh-cost.png)

- [Depth PDF](../backend/tests/out_amr/maximum-depth.pdf)
- [Time-series PDF](../backend/tests/out_amr/time-series.pdf)
- [Metrics, pass/fail checks and provenance](../backend/tests/out_amr/metrics.json)
- [Time-series CSV](../backend/tests/out_amr/time_series.csv)
- [AMR manifest](../backend/tests/out_amr/amr-5m/manifest.json)
- [Uniform manifest](../backend/tests/out_amr/uniform-5m/manifest.json)

DEM SHA-256: `fb5086ce180ad2715c78f6b4d746c9327946cd42ec5ad8961024e6d0e54bdb11`.
Titan2D archive SHA-256:
`4d173502994dc745eaa9392f1e914175fd4a7f0b8b01c3e3fa1ad677e167befc`.
Manifests record code hashes, baseline git commit and working-tree diff hash,
since the feature was tested before commit. Some harness formatting changed
during testing; production numerical code for the completed AMR run was unchanged.

## Reproduce

First prepare the portable Titan2D runtime and Colima DEM using
[the baseline instructions](COLIMA-COMPARISON.md#reproduce-on-windows-with-docker-desktop).
From the repository root, create a fresh output directory; preserve existing
results before replaying. Never overwrite a completed benchmark silently.

```powershell
New-Item -ItemType Directory -Force backend/tests/out_amr/titan2d | Out-Null
Copy-Item backend/tests/colima_titan2d.py backend/tests/out_amr/titan2d/input.py
docker run --rm --mount "type=bind,source=$PWD/backend/tests/out_amr/titan2d,target=/case" --mount "type=bind,source=$PWD/backend/tests/out_colima_comparison/toolchain,target=/work/toolchain,readonly" --mount "type=bind,source=$PWD/dem,target=/dem,readonly" -w /case titan3d-colima-titan2d:4.2.0 bash -c '/work/toolchain/titan2d-v4.2.0/bin/titan -nt 4 input.py > run.log 2>&1'
```

Then from `backend/`:

```powershell
uv run --no-sync python tests/amr_colima.py --model uniform
uv run --no-sync python tests/amr_colima.py --model amr
uv run --no-sync --with h5py --with seaborn --with matplotlib python tests/amr_report.py --check
uv run --no-sync pytest tests/test_amr.py tests/test_amr_cli.py -q
uv run --no-sync --with h5py pytest tests/test_colima_comparison.py -q
uv run --no-sync pytest tests/test_imports.py -v
uv run --no-sync pytest -q
uv run --no-sync ruff check --fix src/
uvx ty check src/
```

`--check` enforces the predeclared AMR-versus-uniform budgets and passes for this
run. Add `--check-titan2d` to enforce upstream similarity screening; that command
intentionally exits 1 because the footprint criterion fails, after writing all
artifacts. `--reuse-reference` uses the extracted unchanged reference; omit it
after rerunning Titan2D. Keep generated artifacts, DEM and binary distribution
out of git.

## Use and limits

In the web UI, open **Setup → Resolution and time** and check **Adaptive mesh
refinement (experimental)**. Expand **Numerics** to change the advanced settings.

From `backend/`, run a scenario with AMR enabled:

```powershell
uv run titan3d run --config scenario.yaml --amr
```

Alternatively, enable it in the scenario YAML:

```yaml
numerics:
  dx: 20
  amr: true
```

This example uses adaptive 20–40 m cells and a 20 m output raster. The other
scenario sections (terrain, sources, material and time) are still required.

`--no-amr` overrides a YAML file to use the uniform solver. `dx` always denotes
the finest spacing. Advanced controls expose gradient, buffer, mesh-update
interval and coarsening delay. Results and exported captions state the cell-size
range and conservative output raster; provenance records the settings.

The first increment has no multilevel adaptation, time subcycling, MPI or sparse
terrain/output storage. Coarse terrain is averaged from the fixed finest DEM;
finer output pixels do not add unresolved terrain or flow detail. Uniform cost
estimates in Setup are labelled as uniform references when AMR is selected.
Use the uniform solver for production performance and retain it for accuracy
comparisons. AMR is an opt-in experimental method, not field validation or an
official hazard map.
