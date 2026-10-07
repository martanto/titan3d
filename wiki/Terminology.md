# Model and comparison terminology

Plain-language definitions for the README, model documentation and
[Colima comparison report](../docs/COLIMA-COMPARISON.md). Units and thresholds
below describe this project; comparison reports must state their own conventions.

## Mesh and resolution

**AMR — Adaptive Mesh Refinement** changes computational cell sizes during a
simulation. Cells are refined where more detail is needed, such as near a flow
front or a sharp change in depth, and may be coarsened elsewhere. This concentrates
computation without using the finest resolution throughout the domain. Its cost
and accuracy depend on the refinement rules and numerical implementation.
Titan2D describes its use of AMR in its [official documentation](https://github.com/TITAN2D/titan2d).

In the executed Colima comparison, Titan2D used AMR with a minimum saved cell
size of about **3.533 m**. titan3d used separate **10, 5 and 2.5 m uniform-grid
runs**. AMR remains planned for titan3d; the existing active window does not
refine the mesh. See the [AMR plan](../docs/roadmap/01-adaptive-mesh-refinement.md).

| Term | Meaning in this project |
|---|---|
| Mesh / grid | The computational cells used to represent terrain and flow. |
| Uniform or fixed grid | Every cell has the same size, which stays constant during the run. A fixed grid can still use changing time steps. |
| Grid spacing, Δx or `dx` | The side length of a square computational cell, in metres. Smaller spacing resolves smaller features but increases work. |
| DEM resolution | The spacing of elevation samples in the source terrain raster. Using a finer solver grid interpolates those samples; it does not create new measured terrain detail. |
| Leaf cell | An adaptive cell that has no finer child cells. State integrals use the current leaf cells so coarse parents are not counted again. |
| Refinement / coarsening | Splitting cells into smaller cells / combining them into larger cells. Mass transfer between levels needs conservation checks. |
| Active window | The uniform-grid region currently evaluated around material and sources, with a stencil margin. Cell sizes are unchanged. |
| Viewer detail | Downsampled terrain and flow data sent to the browser. This controls display cost separately from solver grid spacing and full-resolution downloads. |

## Numerical method and time

**Numerical order and cell size describe different choices.** First- and
second-order refer to how a method's error scales with resolution under suitable
smoothness and stability conditions. For smooth solutions, second-order error
can decrease roughly fourfold when spacing is halved, compared with roughly
twofold for first order. Flow fronts and limiters can reduce the achieved order;
second order is not a guarantee of better agreement in every benchmark.

Thus **“Titan2D AMR, first order”** means adaptive cell sizes with the selected
first-order scheme. **“titan3d 5 m, MUSCL second order”** means uniform 5 m cells
with the project's second-order reconstruction and time integrator. This label
describes the Colima run; it does not imply Titan2D only supports first order.

| Term | Meaning in this project |
|---|---|
| Finite-volume method | Updates cell-average mass and momentum using fluxes across cell faces and sources within cells. |
| Reconstruction | Estimates values near cell faces from neighbouring cell averages before calculating fluxes. |
| MUSCL | Monotonic Upstream-centered Schemes for Conservation Laws: the reconstruction family used for spatial accuracy in titan3d. |
| Minmod limiter | Limits reconstructed slopes to suppress artificial oscillations near steep changes. It can reduce local accuracy to first order. |
| Rusanov flux | A numerical estimate of transport through a cell face, using the states on both sides and an estimated maximum wave speed. |
| Hydrostatic reconstruction | Adjusts face states for changes in bed elevation, helping preserve nonnegative depth and resting water over uneven terrain. |
| Well-balanced | A discretisation that preserves a chosen physical equilibrium, such as a lake at rest, without generating artificial motion. |
| SSP-RK2 | Strong Stability Preserving, second-order Runge–Kutta: titan3d's two-stage time-integration method, also called Heun's method here. |
| CFL | Courant–Friedrichs–Lewy condition. The configured Courant number limits time-step size using cell spacing and estimated wave speeds. It is a stability control, not a friction parameter. |
| Adaptive time step, Δt | A time step adjusted as wave speeds and sources change. It does not imply AMR. |
| Saved state / output frame | A snapshot written at an output time. Many solver steps may occur between two frames. |
| Numerical diffusion | Smoothing introduced by the discretisation, which can spread flow margins or reduce peaks. It is separate from physical material behaviour. |
| Conservative transfer | Moving cell-average fields between grids while preserving their area-weighted integrals, including depth × area for volume. |
| Resolution sensitivity / convergence | Sensitivity means results change when the grid changes. Convergence requires evidence that errors diminish systematically under controlled refinement; one closer result is insufficient. |

For background on adaptive finite-volume grids, see the
[AMR algorithm documentation](https://www.clawpack.org/amr_algorithm.html).
The [titan3d numerical method](Titan2D.md#numerical-method-titan3d) describes the
implemented scheme.

## Terrain, physics and release

| Term | Meaning in this project |
|---|---|
| DEM | Digital Elevation Model: a raster of terrain elevation. It is not satellite imagery. |
| CRS | Coordinate Reference System: defines the meaning of spatial coordinates. Source longitude/latitude and projected metre coordinates are different representations. |
| UTM | Universal Transverse Mercator: a projected coordinate system using eastings and northings in metres. Colima uses UTM zone 13N, EPSG:32613. |
| Depth-averaged flow | Represents a shallow layer by depth and velocity averaged through that depth, rather than resolving a full 3D velocity field. The 3D viewer does not turn the solver into a full 3D model. |
| Depth, `h` | Modelled material thickness in metres; distinct from bed elevation `b` in metres above the elevation datum. |
| Momentum fields, `hu` and `hv` | Depth multiplied by eastward/northward velocity, in m²/s. Velocity is recovered by dividing by depth where material is sufficiently thick. |
| Rheology | The model describing material resistance and movement. titan3d supports Coulomb and Voellmy–Salm basal resistance. |
| Basal friction, φ_bed | Friction between flow and terrain. In the Coulomb model the resistance depends on tan φ_bed and the effective normal loading. |
| Internal friction, φ_int | Friction within the granular material. It enters titan3d's earth-pressure coefficient; the additional internal-friction shear term is not yet implemented. |
| Savage–Hutter earth pressure, `k` | A coefficient describing depth-integrated granular pressure, with active/passive values for spreading/converging flow. The hydrostatic option sets k = 1. |
| Voellmy–Salm | Basal resistance combining a dry-friction coefficient μ and speed-squared drag controlled by ξ [m/s²]. Smaller ξ gives stronger drag at the same speed. |
| Bed curvature | Bending of the terrain surface. The curvature term changes effective normal loading and therefore resistance as flow follows bends. |
| Pile | Material present at t = 0. A cylinder has constant height within its footprint; a paraboloid tapers from peak height to zero at its radius. |
| Analytic release volume | The continuous geometric volume: πR²H for a circular cylinder, πR²H/2 for a circular paraboloid. Equal volume does not make their depth profiles identical. |
| Discrete initial volume | The volume actually represented by the initial computational cells. It can differ from the analytic volume because of cell sampling. |
| Flux source / vent | Material injected over a specified time interval, optionally carrying initial momentum. |
| Erosion / entrainment | Removal of bed material / incorporation of that material into the moving flow. These processes remain planned for titan3d. |

## Outputs and comparison metrics

| Term | Meaning and interpretation |
|---|---|
| Wet / inundated threshold | A declared depth cutoff for counting flow. Statistics and the Colima comparison use h > 0.1 m. It is a reporting choice, not a physical hazard boundary. |
| Dry threshold, `h_dry` | A numerical cutoff for velocity handling; the titan3d default is 0.001 m. It serves a different purpose from the 0.1 m reporting threshold. |
| Runout / front distance | Farthest straight-line horizontal distance from the reference source centre to a cell centre exceeding the declared depth threshold. It is not distance along a curved flow path; the initial pile already has a nonzero radius. |
| Inundated area | Area of cells exceeding the threshold at the stated instant. Maximum-depth footprint area instead represents cells reached at any included time. |
| Maximum-depth envelope | Largest depth recorded at each location over a specified time window. Different locations can reach their maxima at different times. |
| Sampled envelope | Maximum over saved frames. It can miss a peak between frames; an every-step envelope has denser temporal sampling. State the sampling interval when comparing. |
| Peak speed | Largest speed among the included cells and times. The report uses h > 0.1 m and shared saved times; a raw per-step log diagnostic may use different conventions. |
| Footprint | The set of locations where the chosen depth field exceeds the threshold. Declare whether the field is instantaneous or an envelope, and whether the release area is masked. |
| IoU | Intersection over Union: overlapping footprint area divided by the area covered by either footprint. 1 (100%) means identical footprints; 0 means no overlap. |
| Wet union | Locations counted as wet in either result. Evaluating errors here includes disagreement at flow margins instead of allowing large dry regions to hide it. |
| MAE | Mean Absolute Error: average absolute candidate-minus-reference difference, in the field's units. For depth, units are metres. |
| RMSE | Root Mean Square Error: square root of the mean squared differences. It weights larger errors more strongly than MAE and has the field's units. |
| Bias | Mean signed candidate-minus-reference difference. Positive depth bias means the candidate is thicker on average over the stated evaluation region. |
| Difference map, Δh | Candidate depth minus reference depth at aligned locations and matching time conventions. In the report, positive means titan3d has greater maximum depth. |
| Mass / volume balance | Checks retained plus outflow against released material. With constant density and no entrainment, volume provides the corresponding mass-budget check. Declare whether percentages use analytic or discrete release volume. |
| Outflow | Material crossing a computational boundary, counted separately from material retained in the domain. |
| H/L mobility | Vertical elevation drop H divided by horizontal travel L. Here H is an elevation drop, not initial pile thickness. It is an approximate mobility diagnostic, not a direct measurement of friction. |
| Screening criterion | A chosen benchmark threshold, such as a maximum relative runout error or minimum IoU. Passing selected criteria does not establish general numerical equivalence. |
| Verification / validation / calibration | Verification checks equations and numerical implementation; validation compares a model with physical observations; calibration adjusts parameters using evidence. Comparing two solvers alone is not field validation. |
| Provenance | Recorded inputs, software versions, code revision and file hashes needed to identify and reproduce a run. |

## Execution terms

| Term | Meaning |
|---|---|
| NumPy / Numba | NumPy provides array operations; Numba compiles numerical Python kernels for execution on the CPU. These are execution backends, not different friction laws. |
| float32 / float64 | Floating-point formats with different numerical precision and memory costs. More precision does not compensate for an unsuitable grid or physical model. |
| OpenMP / MPI | Parallel-execution approaches using threads / communicating processes. The recorded Colima Titan2D run used four OpenMP threads, not an MPI run. |
| XDMF / HDF5 | XML metadata describing a mesh and fields / a binary data container. Titan2D saves adaptive-cell geometry, depth and momentum using these formats. |
