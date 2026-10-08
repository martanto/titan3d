# One-level adaptive mesh: numerical contract

## Scope

The opt-in solver uses square parent cells of width `2 dx` and rectangular
2 × 2 child patches of width `dx`. `dx` remains the finest solver and output
spacing. There is one refinement level, a shared time step and no subcycling.
The existing uniform solver remains the default and the fine-grid reference.

Each location belongs to exactly one leaf cell. An explicit face graph joins
leaves; a coarse face is split into two fine-length segments. This replaces
duplicated patch ghost storage with direct neighbour reads. Every segment has
one numerical flux, used by both owners. Consequently no separate post-step
reflux register is needed: coarse updates already use the sum of fine fluxes
at **both** RK stages. Boundary faces use transmissive exterior states.

## Calculations to verify

The [step-by-step MUSCL guide](MUSCL.md) explains the uniform-grid method and
the changes needed for AMR gradients and split faces.

For leaf area A and segment length L, the finite-volume update is
`dU/dt = -sum(sign F L)/A + S`. Internal mass and flat-bed momentum fluxes
cancel pairwise after multiplying by area, including coarse/fine interfaces.
The shared CFL step is bounded by the sum of directional wave speeds:
`dt <= CFL min(dx_leaf / (|u| + |v| + 2 sqrt(k_max g h)))`.
A donor-cell draining limiter bounds outgoing volume in each Euler stage;
it scales the shared numerical flux. Only roundoff-sized negative depths are
clamped; materially negative depths fail rather than being repaired by clipping.

MUSCL slopes use minmod of neighbour differences divided by centre distance.
Neighbours on a split face are weighted by segment length. Reconstruct depth,
bed and velocities separately, as in the uniform solver. Hydrostatic states
are `h* = max(0, h_face + b_face - max(b_L, b_R))`; normal momentum includes
the side-specific correction `k g (h_face² - h*²)/2`. The within-cell bed
source is `-g h grad(b)`. For k = 1 and constant free surface, minmod's odd
symmetry gives `grad(h) = -grad(b)` and pressure and bed forces cancel.
Do not extend this lake-at-rest guarantee to variable Savage–Hutter pressure.

Restriction averages depth and both momenta over four equal-area children.
Terrain is the average of the fixed finest DEM cells. Prolongation chooses a
water level z such that `sum(max(z - b_child, 0))/4 = h_parent`, then assigns
the parent velocity to the resulting child depths. This preserves nonnegative
depth, volume and both momenta, including partially dry children. It preserves
a fully wet resting lake; partially dry coarse cells lose subcell detail.
Never renormalise the entire release to conceal transfer errors.

Terrain slope/curvature for friction is area-averaged from the fixed finest
terrain geometry. Piles and vent profiles are sampled once on that finest grid;
vent footprints stay refined, including delayed sources. Source increments use
the exact overlap with their active time interval. Mesh changes occur only
between complete RK steps. Historical maxima remain on the fixed output grid.

Fronts and relative depth/velocity gradients trigger refinement, with a
coarse-cell buffer, periodic regridding and delayed coarsening for hysteresis.
Odd domain edges stay fine; no cells outside the original domain are introduced.
Outputs conservatively prolong leaf depth/momentum to the regular finest grid.
Native leaf statistics and raster statistics must be identified separately.
Rasterisation does not add terrain or flow detail to coarse solver cells.

## Upstream and primary references

Review the pinned [Titan2D adaptation controller](https://github.com/TITAN2D/titan2d/blob/b86f17412fe4dd180c2125eabd85bf6554328a79/src/adapt/hadpt.C),
[refinement](https://github.com/TITAN2D/titan2d/blob/b86f17412fe4dd180c2125eabd85bf6554328a79/src/adapt/refine2.C)
and [coarsening](https://github.com/TITAN2D/titan2d/blob/b86f17412fe4dd180c2125eabd85bf6554328a79/src/adapt/unrefine.C).
Its controller considers element error, pile boundaries and multiple buffer
thresholds, with a generation limit; each parent splits into four children.
Our one-level rectangular mesh is not a port of its multilevel mesh controller.
The existing Colima reference uses Titan2D's first-order scheme.

[Berger and Colella (1989)](https://doi.org/10.1016/0021-9991(89)90035-1)
establish conservative coarse/fine flux matching.
[Audusse et al. (2004)](https://doi.org/10.1137/S1064827503431090)
provide the hydrostatic reconstruction and positivity/well-balancing framework.
These references motivate the design; tests must establish the implemented
properties, particularly at changing mesh interfaces.

## Predeclared verification budgets

- Float64 closed-domain mass and flat-bed momentum residual: at most 1e-10
  relative; mass plus signed boundary outflow plus sources: at most 1e-8.
  Float32 mass budget: 1e-5 relative.
- Resting hydrostatic lake: momentum and free-surface error below 1e-9 in
  float64, across mixed interfaces and repeated split/merge operations.
- Nonnegative finite depth and finite momentum at every stage; wet/dry tests
  must exercise nonzero mixed-interface flux and boundary outflow.
- NumPy/Numba float64 parity: absolute 1e-10, relative 1e-10.
- Synthetic moving-flow comparison with the unchanged uniform fine solver:
  wet-union depth RMSE at most 0.1 times its peak depth, runout within two finest
  cells and inundated area within 10% at the declared final time.
- Colima 0–150 s, saved every 1 s: AMR versus uniform 5 m sampled maximum-depth
  footprint IoU at least 0.90, wet-union RMSE at most 0.25 m, final runout within
  5%, peak saved speed within 10%, and mass budget within 0.1%.
  Compare independently with original Titan2D using the existing 10% runout,
  20% peak-speed and 0.70 footprint-IoU screening; report failures honestly.
- Record warm-up separately from timed runtime and include mesh management,
  output and memory costs. Do not claim speedup from reduced leaf count alone.

No fitting of friction, gravity or comparison thresholds to the outcome.
Record limitations and leave release criteria open if any budget fails.
