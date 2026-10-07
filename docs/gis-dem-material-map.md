# GIS input, DEM and material map

How Titan2D reads terrain, and what titan3d needs to match it.
Facts about Titan2D come from its source (github.com/TITAN2D/titan2d, `master`):
`src/main/titan.py` (`setGIS`), `src/gisapi/GisApi.{h,C}`, `configure.ac`, and the
examples in `share/titan2d_examples/`.

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
built `--with-gdal` for this path.

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
   - titan3d: load `matmap.tif` alongside the DEM (see tasks below).

### Calibration caveat

The map is easy; the friction values per class are poorly constrained. Calibrate by
back-analysis: adjust φ_bed per class until simulations reproduce the runout, H/L and
deposit outline of mapped past flows. Without calibration a material map adds complexity,
not accuracy. A single calibrated φ_bed is often the better starting point; add classes
only where the deposit record clearly needs them.

---

## 4. Current state of titan3d

Compared with Titan2D's GIS handling (as of `main` after PR #4):

| Titan2D feature | titan3d | Where |
|---|---|---|
| GDAL raster input | done — tiles stitched, reprojected to local UTM | `core/dem.py` (`stitch_tiles`, `load_domain`) |
| Georeferencing / map coordinates | done — `Grid.crs`, north-up, CRS metres | `core/grid.py` |
| `region_limits` | done, as vent-anchored extents in km (`extents_km`) | `core/dem.py:load_domain` |
| Nodata handling | done — `fillnodata`, domains over `MAX_NAN_FRACTION` rejected | `core/dem.py` |
| Curvature (centripetal) term | done — `bxx`, `bxy`, `byy` in `normal_gravity` | `core/curvature.py` |
| GRASS input | not supported (not needed; GDAL covers it) | — |
| **Material map** (`use_gis_matmap`) | **missing** — `phi_bed_deg` is one float; `tan_bed` is a scalar | `core/params.py`, `core/solver.py`, `core/rheology.py`, `core/kernels_numba.py` |

---

## 5. Implementation task: material map

Follow `CLAUDE.md` working rules (new `ft/` branch, changelog entry, `ty`, `ruff`,
`tests/test_imports.py` after module changes, regenerate `openapi.json` if schemas change).
Do it in small commits, core first, then API, then frontend.

### 5.1 Core (no web deps)

- **Loading.** In `core/dem.py`, add `load_matmap(path, grid) -> np.ndarray` (int). Reproject
  the category raster onto the domain grid with **nearest-neighbour** resampling (never
  bilinear — codes are categories). Code 0 = nodata.
- **Parameters.** `FlowParams` keeps `phi_bed_deg: float` as the default and gains
  `bed_frict_by_code: dict[int, float] | None`. Cells whose code is 0 or absent from the
  dict use `phi_bed_deg`.
- **Per-cell friction.** Build `tan_bed` as a full-grid `FloatArray` once in the solver
  (scalar case: `np.full(shape, tan φ)` or keep a scalar fast path).
  - `rheology.apply_friction`: index `tan_bed[window]` when it is an array.
  - `kernels_numba.py`: pass the array and read `tan_bed[j, i]` inside the loop.
  - Kernel factory signatures in `solver.py` (`NumpyKernels`, `NumbaKernels`) change from
    `tan_bed: float` to `float | FloatArray`.
- **Earth pressure.** `earth_pressure_coefficients(phi_int, phi_bed)` assumes scalar
  φ_bed. Options: (a) evaluate k_act/k_pas per cell (array), or (b) keep the scalar using
  the area-weighted or minimum φ_bed. Prefer (a) if it does not slow the kernel; record the
  choice in the changelog. Guard `1 − cos²φ_int / cos²φ_bed` with `np.maximum(…, 0)`.
- **Validation.** Error if `bed_frict_by_code` has a φ_bed > φ_int (Savage–Hutter needs
  φ_bed ≤ φ_int).

### 5.2 Tests (`backend/tests/`)

- `test_matmap.py`
  - Pile on a uniform 10° plane; left half code 1 (φ_bed 5°), right half code 2 (φ_bed 20°).
    Mass on the right stays at rest, mass on the left slides.
  - Scalar run ≡ material map with a single code set to the same φ_bed (bit-identical or
    within 1e-12).
  - `load_matmap` uses nearest-neighbour: codes after reprojection are a subset of the
    input codes.
- Extend `test_numba_parity.py` with a material-map case.
- Lake-at-rest and mass-balance tests must still pass.

### 5.3 API

- `ScenarioRequest` (single source of truth) gains an optional material map: upload
  reference (stored like DEMs) plus `bed_frict_by_code`. Update `scenario_yaml.py`,
  `openapi.json`, and `npm run gen:api`.

### 5.4 Frontend

- Setup view: upload a material raster, show detected codes, and a small table to enter
  φ_bed per code (default = global φ_bed).
- Results/setup: a "Material" surface mode colouring terrain by code, from the tokens only.
- Caption states that friction varies by material map and lists the per-code values.

### 5.5 Validation against Titan2D

- Titan2D ships `share/titan2d_examples/inclined/Coulomb_MatMap` (GRASS) with three
  classes (27°, 35°, 20°). Export `inclined` and `inclined_Mat` to GeoTIFF
  (`r.out.gdal`), run the same pile in titan3d, and compare deposit position and runout.
