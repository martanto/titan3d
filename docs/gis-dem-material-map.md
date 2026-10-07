# GIS input, DEM and material map

Reference for terrain input and spatially varying friction: how Titan2D does it, what
titan3d already does, and the remaining task (material map).

Sources:
- Titan2D (github.com/TITAN2D/titan2d, `master`): `src/main/titan.py` (`setGIS`),
  `src/gisapi/GisApi.{h,C}`, `configure.ac`, `share/titan2d_examples/`.
- titan3d `main` at `c58b18e` (after PR #4): `backend/src/titan3d/core/*`, `api/*`, `db/*`,
  `frontend/src/{ui,scene}/*`, `wiki/Titan2D.md`, `wiki/Backend.md`, `README.md`.

Related: `wiki/Titan2D.md` (equations, parameters, calibration, titan3d vs Titan2D table) —
do not duplicate it; update it when the material map lands (section 5.7).

---

## 1. GIS formats: `GIS_GRASS` and `GDAL`

Titan2D reads terrain through `sim.setGIS(gis_format=...)`. Two formats are supported.

```
              sim.setGIS(gis_format=...)
                        │
         ┌──────────────┴──────────────┐
    'GIS_GRASS'                      'GDAL'
         │                             │
   GRASS database:               a single raster file
   gis_main/                     gis_map='dem.tif'
     gis_sub/       (location)   (GeoTIFF or any GDAL
       gis_mapset/  (mapset)      raster format)
         cell/gis_map (raster)
         │                             │
         └──────────────┬──────────────┘
                 Titan2D GIS API
     Get_elevation · Get_slope · Get_curvature · Get_xmax …
```

**GRASS GIS** stores data in a fixed folder structure: database → location → mapset → raster.
Titan2D has its own reader for these files (`cellhd/`, `cats/`, `cell/`), so GRASS itself
does not need to be installed.

```python
sim.setGIS(gis_format='GIS_GRASS', gis_main='../../dem',
           gis_sub='colimafinemini', gis_mapset='PERMANENT', gis_map='colima')
```

**GDAL** is the standard raster I/O library (used by QGIS and rasterio). Titan2D must be
built `--with-gdal` for this path. titan3d reads rasters through rasterio, whose wheels bundle
GDAL, so no separate GDAL install is needed (see README → Requirements).

```python
sim.setGIS(gis_format='GDAL', gis_map='../../dem/colimafinemini.geotiff')
```

General options for both:

- `region_limits=(min_x, min_y, max_x, max_y)` restricts the simulation to part of the map.
  Default `None` uses the whole map.
- `gis_vector` is an optional vector layer.

### Which is better?

Neither, for the simulation itself. Both feed the same API, so the same DEM gives the same run.

| | GIS_GRASS | GDAL |
|---|---|---|
| Input | GRASS folder tree (main/location/mapset/map) | one file (GeoTIFF etc.) |
| GRASS install needed | no (built-in reader) | no, but Titan2D must be built with GDAL |
| Material map (`use_gis_matmap`) | supported | elevation only, as far as the source shows |
| DEM prep tools | GRASS `r.*` modules | QGIS, `gdalwarp`, rasterio |
| Portability | folder tree, easy to break | single file |
| Bundled examples | most | one (`colimafinemini/Coulomb_GeoTIFF`) |

The one functional difference: the material-map loader in `GisApi.C` reads GRASS files
(`cellhd/`, `cats/`, `cell/`). No GDAL path for it was found, so spatially varying bed
friction in Titan2D appears to need GRASS format.

Rule of thumb: use GDAL when only elevation is needed; use GRASS when a material map is
needed or the DEM is already prepared in GRASS.

What matters more than the format:

- **CRS** must be projected in metres (e.g. UTM). Lat/long degrees break slopes and distances.
- **DEM quality**: fill nodata holes, remove spikes, pits and stripes. A post-eruption DEM
  that reflects current morphology matters more than the file format.

---

## 2. What the DEM is used for

The equations behind each item (driving term, curvature `g_eff`, earth pressure) are in
`wiki/Titan2D.md`; this section only maps the DEM's roles.

```
 DEM b(x,y)
   ├─ elevation ─────► bed level the flow moves over
   ├─ slope ∂b/∂x,∂b/∂y ─► gravity driving force  (−g h ∇b)
   ├─ curvature ─────► centripetal term: extra basal normal
   │                   stress → extra friction where the bed
   │                   curves (channel bends, slope breaks)
   ├─ extent ────────► computational domain and initial mesh;
   │                   AMR refines down to the DEM resolution
   └─ map coords ────► piles, flux sources and outputs are
                       placed in real coordinates (e.g. UTM),
                       so results overlay in GIS
```

DEM resolution limits the model: a 30 m DEM cannot resolve a 10 m-wide channel, and mesh
refinement finer than the DEM adds no terrain detail.

---

## 3. Material map

A material map is a second raster on the **same grid as the DEM**. Each cell holds an
integer code for the ground surface type, and each code gets its own basal friction angle
φ_bed.

```
  DEM (elevation, m)           Material map (codes)       φ_bed used
  ┌───────────────────┐        ┌───────────────────┐
  │ 2900 2850 2800 …  │        │ 1  1  1  2  2  2  │      1 → 27°  summit lava/rock
  │ 2700 2600 2450 …  │   +    │ 1  2  2  2  3  3  │  ──► 2 → 35°  rough talus
  │ 2100 1900 1700 …  │        │ 2  2  3  3  3  3  │      3 → 20°  smooth old PDC
  └───────────────────┘        └───────────────────┘
       same grid, same extent, same CRS
```

### In Titan2D

Example `share/titan2d_examples/inclined/Coulomb_MatMap`:

- DEM raster `inclined`; material raster `inclined_Mat` (DEM name + `_Mat`) in the same mapset.
- Categories file `cats/inclined_Mat` labels codes `1:Mat 1`, `2:Mat 2`, `3:Mat 3`.

```python
sim.setMatModel(model='Coulomb', int_frict=37.0,
                use_gis_matmap=True,
                bed_frict={"Mat1": 27.0, "Mat2": 35.0, "Mat3": 20.0})
```

### How to make one

No ready-made dataset exists; build it from knowledge of the volcano's surface.

```
 sources                       classify               rasterize to DEM grid
 ─────────────────────         ─────────────          ─────────────────────
 geological map of volcano ─┐
 deposit maps (recent       │   polygons with a       integer raster, codes 1..N
   eruptions, PDC, lahar)   ├─► class per polygon ──► same extent, cell size,
 land cover (e.g. ESA       │   (QGIS digitize or     CRS as the DEM
   WorldCover 10 m)         │    image classification)
 satellite imagery / field ─┘
```

1. **Choose 3–5 classes** based on how the flow interacts with the surface, not rock age:
   bare lava/rock, coarse talus/block fields, smooth older PDC/ash, vegetated or cultivated
   slopes, river channels.
2. **Digitize polygons in QGIS** from PVMBG geological and hazard (KRB) maps, past deposit
   outlines, or land cover. Add an integer field `code` = 1…N.
3. **Rasterize onto the DEM grid exactly** (same extent `-te`, cell size `-tr`, CRS):
   ```bash
   gdal_rasterize -a code -te XMIN YMIN XMAX YMAX -tr 30 30 \
                  -ot Byte -a_nodata 0 classes.gpkg matmap.tif
   ```
4. **Use it**
   - Titan2D (GRASS): `r.in.gdal input=matmap.tif output=<dem>_Mat`, then `r.category` for labels.
   - titan3d: not supported yet; see section 5.

### Calibration caveat

The map is easy; the friction values per class are poorly constrained. Calibrate by
back-analysis: adjust φ_bed per class until simulations reproduce the runout, H/L and
deposit outline of mapped past flows. Without calibration a material map adds complexity,
not accuracy. A single calibrated φ_bed is often the better starting point; add classes
only where the deposit record clearly needs them.

---

## 4. titan3d today (main @ c58b18e)

### 4.1 DEM pipeline

```
 upload GeoTIFF tiles          stitch_tiles()                 load_domain()
 POST /api/dems  ───────────►  inspect CRS (none → EPSG:4326  ──► vent-anchored box
 or dem/ (built-in,            if bounds are lon/lat, e.g.        W/E/S/N km (DomainIn)
 "Semeru — DEMNAS 0.27″")      DEMNAS); warp to 1st tile CRS;     reproject → local UTM
                               merge bilinear → float32 NaN       (utm_crs_for), dx m,
                               mosaic.tif + MosaicInfo            bilinear; reject >0.5 %
                               (summit, zmin, sha256)             nodata, else fillnodata
                                                                  → Grid(b, dx, x0, y0, crs)
```

| Titan2D | titan3d | Where |
|---|---|---|
| `gis_format='GDAL'` | GeoTIFF tiles via rasterio (GDAL bundled); multi-tile stitching | `core/dem.py:stitch_tiles`, `api/controllers/dem_controller.py` |
| `gis_format='GIS_GRASS'` | not supported; export GRASS rasters with `r.out.gdal` | — |
| Map coordinates | `Grid(b, dx, x0, y0, crs)`, north-up, local UTM metres; sources given in lon/lat and projected | `core/grid.py`, `core/dem.py:load_domain`, `lonlat_to_xy` |
| `region_limits` | vent-anchored extents in km (`DomainIn.west_km…north_km`, defaults 6/16/14/6) | `api/schemas/scenario.py:DomainIn` |
| Nodata | sentinels (< −1000, declared nodata) → NaN; domains > `MAX_NAN_FRACTION` (0.5 %) rejected; small gaps `fillnodata` | `core/dem.py` |
| Slope, curvature | `bed_geometry` → `cos_theta`, `bxx`, `bxy`, `byy`; `normal_gravity` | `core/curvature.py` |
| Outputs in map coords | GeoTIFF max depth/speed with `grid.crs`; inundation GeoJSON/KML in EPSG:4326 | `core/export.py` |
| Provenance | DEM SHA-256, code version, numerics stored per run | `jobs.provenance_json` |
| **Material map** | **missing** — one `phi_bed_deg` for the whole run (`wiki/Titan2D.md` → Limitations: "Constant material properties") | see 4.2 |

### 4.2 Where scalar φ_bed is baked in

| Place | Current code | Impact of per-cell φ_bed |
|---|---|---|
| `api/schemas/scenario.py:MaterialIn` | `phi_bed_deg: float` (0–60) | needs per-code values + map reference |
| `core/params.py:FlowParams` | frozen dataclass, `phi_bed_deg: float` | keep scalar as default; per-cell data does not belong here (not hashable, grid-specific) |
| `core/solver.py:Solver.__init__` | `self.tan_bed = float(np.tan(...))` | becomes a full-grid array (or scalar fast path) |
| `core/rheology.py:apply_friction` | `resist = h * g_eff * tan_bed` on a window | slice `tan_bed[window]` like `geom.cos_theta[window]` |
| `core/kernels_numba.py:friction_numba` | scalar `tan_bed` argument | pass `tan_bed[win]` array, read `tan_bed[j, i]`; `NumbaKernels.friction` slices like `g.cos_theta[win]` |
| `core/rheology.py:earth_pressure_coefficients` | scalars; `max(1 − c2i/c2b, 0)`; φ_bed > φ_int is **allowed** (k_act = k_pas) | per-cell needs `np.maximum` |
| `earth_pressure_block` / `earth_pressure_numba` | scalar `k_act`, `k_pas` on the **padded** block (ghost cells) | per-cell k needs arrays padded exactly like `H` — the trickiest part |
| `rheology.max_earth_pressure` → `Solver.k_max` | CFL wave speed `|u| + √(k_max g h)` | must be the max over all codes, or the time step is unsafe |
| `core/dem.py:_warp`, `stitch_tiles` | hard-coded `Resampling.bilinear`, `float32` | **must not** be reused as-is for codes — bilinear invents codes at class borders |

---

## 5. Task: material map

Follow `CLAUDE.md` working rules: new `ft/` branch, changelog entry per finished task,
`uvx ty check src/`, `uv run ruff check --fix src/`, `tests/test_imports.py` after module
changes, regenerate `openapi.json` + `npm run gen:api` when schemas change, impeccable +
playwright-cli for frontend work. Small commits: core → tests → storage/API → frontend → docs.

### 5.1 Data model

- The material map is co-registered with the terrain, so it belongs with the grid:
  add `material: IntArray | None = None` to `Grid` (codes, same shape as `b`, 0 = none).
- Per-code friction is a run parameter: `MaterialIn.bed_frict_by_code: dict[int, float] | None`
  (keys ≥ 1, values 0–60 like `phi_bed_deg`). Cells with code 0 or a code missing from the
  dict use `phi_bed_deg`. Reject the request if the dict is set but the DEM has no map.
- `FlowParams` stays scalar. The solver builds the per-cell field from `grid.material`
  plus the dict (pass the dict to `Solver` or a small `FrictionField` helper).

### 5.2 Loading (core/dem.py)

- Add a `resampling` (and `dtype`) parameter to `_warp`, default bilinear/float32 so
  existing callers are unchanged.
- `load_material(path, grid) -> IntArray`: warp the category raster onto the domain grid
  (`grid.crs`, `x0`, `y0`, `dx`, shape) with **`Resampling.nearest`**, `uint8`/`int16`,
  nodata → 0, rows flipped like `load_domain` (`[::-1]`, j increases north).
- Material rasters are single files, not stitched tiles; if stitching is ever needed, use
  nearest resampling, never `stitch_tiles` as written.
- Accept rasters in any CRS (reprojected like the DEM). Reject non-integer bands.

### 5.3 Solver and kernels

- `tan_bed`: full-grid array `tan(φ_bed(code))`; keep a scalar fast path when no map is
  used so existing runs are bit-identical.
- Friction: NumPy `apply_friction` and Numba `friction_numba` read `tan_bed[win]`.
- Earth pressure — choose one, record the choice in the changelog and `wiki/Titan2D.md`:
  - **(a) per cell (physically consistent):** precompute full-grid `k_act`, `k_pas`; slice
    and pad them exactly as `H` is padded for the flux block; Numba kernel takes arrays.
  - **(b) per run (simpler first step):** keep scalar `k_act`, `k_pas` from the global
    `phi_bed_deg`; only basal friction varies. Document as an approximation.
- `k_max` = max of `earth_pressure_coefficients(φ_int, φ)` over every φ in use (global and
  all codes) — required for a safe CFL step in either option.

### 5.4 Tests (backend/tests/)

- New `test_material.py`:
  - Split slope: pile on a uniform 10° plane (`core/terrain.py` inclined plane), code 1
    (φ_bed 5°) on one half, code 2 (φ_bed 20°) on the other; mass on the 20° half stays at
    rest, mass on the 5° half slides.
  - Equivalence: map with a single code whose φ_bed equals `phi_bed_deg` ≡ no map
    (identical to round-off).
  - `load_material`: output codes ⊆ input codes after reprojection (proves nearest); rows
    north-up; nodata → 0.
  - `k_max` includes the per-code angles.
- `test_numba_parity.py`: add a material-map case.
- `test_scenario_yaml.py`: round-trip `bed_frict_by_code`.
- Existing lake-at-rest, symmetry, mass-balance and `test_openapi.py` must pass.

### 5.5 Storage and API

- Store the map with its DEM: `data/dems/<dem_id>/material.tif`; record path, codes found
  and SHA-256 on the `dems` row (new columns via `repositories.py` only — it is the only
  module that writes SQL).
- Route: `POST /api/dems/{dem_id}/material` (upload, validate integer band, report codes
  and coverage of the mosaic), `DELETE` to remove; `GET /api/dems/{dem_id}` includes it.
  Keep routes HTTP-only → `dem_controller.py`.
- Submission: `simulation_controller` loads the material onto the domain grid when
  `bed_frict_by_code` is set; provenance stores the material SHA-256 and the code→φ table.
- YAML (`scenario_yaml.py`) and `openapi.json` updated; frontend types regenerated.

### 5.6 Frontend

- Setup → Material panel (next to "Basal friction φ_bed" in `ui/setup.ts`): upload a
  material raster for the selected DEM, list detected codes, a small table φ_bed per code
  (default = global φ_bed), clear option.
- Terrain: add a `"material"` `SurfaceKind` in `scene/engine.ts` / `ui/stage.ts` that
  colours terrain by code (categorical palette from `styles/tokens.css` only — never new
  colours). Export the codes in `terrain_preview` / `viewer_bundle` (`core/export.py`).
- Captions: state that basal friction varies by material map and list code → φ_bed;
  keep "not an official hazard map".

### 5.7 Docs

- `wiki/Titan2D.md`: parameters table (per-code φ_bed), titan3d vs Titan2D table (material
  map ✔), Limitations (remove "constant material properties" or narrow it), calibration
  note (calibrate per class against mapped deposits).
- `wiki/Backend.md`, `wiki/API-Reference.md`, `README.md` (parameters, YAML example).

### 5.8 Validation against Titan2D

- `share/titan2d_examples/inclined/Coulomb_MatMap` (GRASS): three classes, φ_bed
  27°/35°/20°, φ_int 37°, cylinder pile. Export `inclined` and `inclined_Mat` with
  `r.out.gdal`; titan3d has paraboloid piles only, so compare deposit position and
  runout qualitatively, or add a cylinder pile first.

### 5.9 Data for Indonesian volcanoes

- Classes from PVMBG/Badan Geologi geological maps and KRB hazard maps, recent deposit
  outlines (e.g. Semeru 2021–2022 PDC and lahar deposits), and land cover
  (ESA WorldCover 10 m). Rasterize in QGIS onto any grid; titan3d reprojects with nearest.
- Calibrate each class's φ_bed by back-analysis of mapped flows (H/L, runout, outline)
  before relying on it; otherwise use a single calibrated φ_bed.
