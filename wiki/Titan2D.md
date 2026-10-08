# Titan2D and the titan3d model

## About Titan2D

Definitions of AMR, numerical order, CFL, friction models and output metrics are
in [Terminology](Terminology.md).

[Titan2D](https://github.com/titan2d/titan2d) is an open-source simulation code for dry geophysical mass flows over natural terrain: block-and-ash flows, debris avalanches, rock avalanches and similar granular flows. It was developed by the Geophysical Mass Flow Group (University at Buffalo) and collaborators (Patra et al., 2005; Pitman et al., 2003).

Titan2D:
- solves the **depth-averaged Savage–Hutter equations** for a shallow layer of granular material moving over a DEM;
- uses a parallel adaptive-mesh finite-volume method;
- reads GIS elevation data and starts flows from **piles** (initial volumes) or **flux sources** (vents);
- has been used widely for volcanic hazard assessment.

titan3d re-implements the same model family in Python, with the supported physics
and inputs listed below. It replaces the C++ implementation with a tested
NumPy/Numba solver, uniform by default, with opt-in experimental one-level AMR.
AMR changes cell sizes; the uniform solver's active window changes only the
region evaluated. A web app and API sit around the solver. The
[AMR verification report](../docs/AMR-VERIFICATION.md) documents fine-grid
fidelity, costs and the remaining failed Titan2D footprint screening.

## Governing equations

The flow is a shallow layer of depth `h(x, y, t)` and depth-averaged velocity `(u, v)` over the bed `b(x, y)`:

```
∂h/∂t  + ∂(hu)/∂x + ∂(hv)/∂y                               = S_h
∂(hu)/∂t + ∂(hu² + ½ k g h²)/∂x + ∂(huv)/∂y                = −g h ∂b/∂x − F_x
∂(hv)/∂t + ∂(huv)/∂x + ∂(hv² + ½ k g h²)/∂y                = −g h ∂b/∂y − F_y
```

- **Earth-pressure coefficient `k`** (Savage & Hutter, 1989): `k_act/pas = 2 (1 ∓ √(1 − cos²φ_int / cos²φ_bed)) / cos²φ_int − 1`. The active value applies where the flow spreads (∇·u ≥ 0) and the passive value where it converges. Choosing *hydrostatic* sets `k = 1`.
- **Basal resistance `F`**, directed against the velocity:
  - **Coulomb** (Titan2D's default): `|F| = h g_eff tan φ_bed`.
  - **Voellmy (–Salm)**: `|F| = h g_eff μ + g |u|² / ξ`.
- **Normal gravity with bed curvature** (centripetal term): `g_eff = cosθ (g + u² b_xx + 2uv b_xy + v² b_yy)`, clamped at ≥ 0. Flow is pressed into concave bends and lightened over convex breaks.
- **Sources `S_h`:** a paraboloid pile `h = H (1 − r²/R²)` at t = 0, and flux sources adding `influx · (1 − r²/R²)` per second during `[start, start + duration]`, optionally with an initial speed and direction.

**Assumptions:**
- dry, incompressible, cohesionless material of constant density;
- a shallow layer (depth ≪ length);
- no erosion or deposition other than stopping, and no air or fluid phase (single phase).

## Parameters

| Parameter | Symbol | Physical meaning | Effect on the result |
|---|---|---|---|
| Basal friction angle | φ_bed | Friction between the flow and the bed (Coulomb) | **The main control on runout.** A Coulomb flow stops near where its mobility H/L (drop over horizontal travel) reaches tan φ_bed. Lower φ_bed means longer, thinner flows. |
| Internal friction angle | φ_int | Friction inside the granular mass | Through k it sets lateral spreading: a higher φ_int gives larger passive pressure in converging zones and narrower deposits. Must be ≥ φ_bed for the Savage–Hutter formula to differ between active and passive. |
| Voellmy μ | μ | Dry-friction coefficient (Voellmy) | Like tan φ_bed; controls where the flow stops |
| Voellmy ξ | ξ | Turbulence coefficient (m/s²) | Velocity-squared drag; lower ξ means more drag and lower peak speeds |
| Pile thickness and radius | H, R | Initial collapse geometry, volume π R² H / 2 | Volume and initial potential energy |
| Vent influx, duration, radius | — | Extrusion rate and footprint | Sustained supply (dome or lava-front collapse) |
| Initial speed and direction | — | Momentum of vent material | Launches material in a chosen direction |
| Curvature term | — | On/off | Usually on; matters in incised channels |
| Grid spacing | Δx | Numerical resolution | Finer grids resolve channels and margins. Halving Δx costs about 8× (4× cells, 2× time steps). |
| Courant number | CFL | Stability margin of the time step | 0.4 by default; lower is more robust but slower |
| Dry threshold | h_dry | Depth below which velocity is zeroed | Numerical; rarely changed |

Ranges and defaults for every field are in the README's *Parameters* section and in [API Reference → Schemas](API-Reference.md#schemas).

### Calibration

- **Energy-line reasoning:** for a Coulomb flow the apparent friction H/L ≈ tan φ_bed. Compare the simulated **H/L** (shown next to tan φ_bed in Results) with mapped deposits of past events. Adjust φ_bed until runout and inundated area match, then check the deposit shape and the speeds.
- **Volume dependence:** larger collapses travel further. Field H/L values often fall with volume, so calibrate φ_bed for a volume range rather than one number.
- **Resolution:** calibrate at the resolution you intend to use for hazard runs. Coarse grids smear channels and change effective mobility.
- **Report everything:** the Results caption and provenance list the parameters, grid, DEM hash and code version. Keep the YAML of every scenario you rely on.

The defaults (φ_bed 24°, φ_int 34°) come from the original demo and give short runouts at Semeru. Long-runout block-and-ash flows usually need much lower basal friction.

## Numerical method (titan3d)

Grid spacing and numerical order are separate: a uniform 5 m grid specifies cell
size, while second order describes the method's expected error scaling for smooth
solutions. Limiters and flow fronts can reduce the achieved order. See
[mesh and resolution](Terminology.md#mesh-and-resolution) and
[numerical method and time](Terminology.md#numerical-method-and-time).

| Aspect | titan3d |
|---|---|
| Grid | Uniform square cells in the local UTM zone of the release (EPSG:326zz/327zz) |
| Reconstruction | MUSCL with minmod limiter, of depth, bed and velocity |
| Bed source | Hydrostatic reconstruction (Audusse et al., 2004), which is well-balanced with h ≥ 0. Depth and bed are reconstructed separately so thin flows are not trapped on steep slopes (cf. Delestre et al., 2012). |
| Flux | Rusanov (local Lax–Friedrichs) with wave speed `|u| + √(k g h)` |
| Time integration | SSP-RK2 (Heun), adaptive CFL time step, also limited while vents inject |
| Friction | Implicit stopping step after each stage: momentum magnitude is reduced by dt·|F| and clamped at zero, so material stops on slopes flatter than φ_bed |
| Boundaries | Transmissive. Material leaving the domain is counted as outflow, and in-domain plus outflow equals released volume. |
| Speed | Only the bounding box of cells holding material is computed (exact); Numba parallel kernels; float64 or float32 |

## titan3d vs Titan2D

The [step-by-step MUSCL guide](../docs/MUSCL.md) explains the implemented
reconstruction, limiter, hydrostatic adjustment and flux update.

| Feature | Titan2D | titan3d |
|---|---|---|
| Governing equations | Depth-averaged Savage–Hutter | Same |
| Coulomb basal friction | ✔ | ✔ |
| Voellmy–Salm | ✔ | ✔ |
| Pouliquen–Forterre, two-phase Pitman–Le | ✔ | Not yet |
| Earth pressure (active/passive) | ✔ | ✔ (Savage–Hutter, or hydrostatic) |
| Bed-curvature term | ✔ | ✔ |
| Internal-friction shear term `sgn(∂u/∂y) k ∂(g h)/∂y sin φ_int` | ✔ | Not yet |
| Piles | Paraboloid and cylinder | Paraboloid (several per scenario) |
| Flux (vent) sources | ✔ | ✔ (start, duration, initial velocity) |
| Mesh | Adaptive (AMR), parallel (MPI) | Uniform active window by default; experimental one-level 2:1 AMR; Numba kernels; no MPI |
| DEM input | GIS rasters | GeoTIFF tiles; multi-tile stitching; automatic UTM reprojection |
| Outputs | Simulation files, max-height maps | GeoTIFF max depth/speed, GeoJSON/KML inundation, frames, browser playback, PNG figures |
| Interface | Command line / Python input scripts | Web app, REST API, YAML configs, CLI |
| Provenance | — | Code version, git commit, DEM SHA-256 and numerics stored with every run |

## Verification cases

These are standard checks for shallow-flow solvers, all run in the test suite:

- **Lake at rest over a bump:** a still, frictionless pool must stay still (|hu| < 1e-10). This tests well-balancing.
- **Pile on a slope flatter than φ_bed:** the pile must not slide. This tests the Coulomb stopping step.
- **Symmetric release on an inclined plane:** the solution stays mirror-symmetric to 1e-10.
- **Mass balance with outflow:** in-domain plus outflow equals released volume to 1e-5.
- **Curvature:** the term is zero on a plane and `g + u²/R` on a cylindrical bed.
- **Vent volume:** the injected volume equals the footprint integral × influx × duration exactly, whatever the time step.

## Limitations

- **Single-phase dry granular flow:** no pore fluid, dilute surges, ash-cloud or co-PDC phases, erosion or entrainment.
- **Constant material properties** for the whole run.
- **Uniform grid** without adaptive refinement, so very large domains at fine resolution are costly.
- **Model output, not a hazard map:** hazard assessment needs calibration, scenario ranges and expert judgement.

## References

- Savage, S. B., & Hutter, K. (1989). The motion of a finite mass of granular material down a rough incline. *Journal of Fluid Mechanics*, 199, 177–215.
- Pitman, E. B., Nichita, C. C., Patra, A. K., Bauer, A. C., Sheridan, M. F., & Bursik, M. (2003). Computing granular avalanches and landslides. *Physics of Fluids*, 15(12), 3638–3646.
- Patra, A. K., Bauer, A. C., Nichita, C. C., Pitman, E. B., Sheridan, M. F., Bursik, M., et al. (2005). Parallel adaptive numerical simulation of dry avalanches over natural terrain. *Journal of Volcanology and Geothermal Research*, 139, 1–21.
- Pitman, E. B., & Le, L. (2005). A two-fluid model for avalanche and debris flows. *Philosophical Transactions of the Royal Society A*, 363, 1573–1601.
- Audusse, E., Bouchut, F., Bristeau, M.-O., Klein, R., & Perthame, B. (2004). A fast and stable well-balanced scheme with hydrostatic reconstruction for shallow water flows. *SIAM Journal on Scientific Computing*, 25(6), 2050–2065.
- Delestre, O., Cordier, S., Darboux, F., & James, F. (2012). A limitation of the hydrostatic reconstruction technique for shallow water equations. *Comptes Rendus Mathématique*, 350, 677–681.
- Crameri, F., Shephard, G. E., & Heron, P. J. (2020). The misuse of colour in science communication. *Nature Communications*, 11, 5444.
- Titan2D source and documentation: https://github.com/titan2d/titan2d
