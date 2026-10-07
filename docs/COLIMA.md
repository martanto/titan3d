# Colima example

Open **Examples** in the application (`#/examples`). Download the linked upstream
GeoTIFF, select it in the page, choose Coulomb or Voellmy–Salm, and open Setup.
Review the terrain and parameters there before running. Setup's **Download config**
exports the full scenario YAML with the registered local DEM identifier.

Source revision: `b86f17412fe4dd180c2125eabd85bf6554328a79` in
[TITAN2D/titan2d](https://github.com/TITAN2D/titan2d/tree/b86f17412fe4dd180c2125eabd85bf6554328a79/share/titan2d_examples).
Parameters come from `colimafinemini/Coulomb_GeoTIFF/input.py` and
`colimafinemini/Voellmy_Salm/input.py`; terrain is `dem/colimafinemini.geotiff`.
Downloads and terrain uploads remain local; DEM files are not committed.

The raster is EPSG:32613, 900 × 900 cells, with 5 m pixels and bounds
(641500, 2154500, 646000, 2159000) m. The release centre (644956, 2157970) m
converts to (-103.61857604070536, 19.511146722180904) degrees using rasterio.

The upstream cylinder has height 30 m and radius 55 m. Titan3D's paraboloid
has peak height 60 m and the same radius, preserving volume π × 55² × 30 m³.
Coulomb uses basal/internal friction 27°/37°; Voellmy uses μ=0.35, ξ=120 m/s².
The adaptation uses a 10 m fixed grid, a 3.4 km west/south and 1 km east/north
domain, 300 s duration and 1 s output. These replace upstream AMR, first-order
numerics and iteration limits (5000 Coulomb / 30000 Voellmy). Upstream Voellmy
outputs every 100 s. Curvature and pressure retain Titan3D defaults.

This example is an adaptation; matching parameters does not establish numerical
equivalence to Titan2D or field validation.
