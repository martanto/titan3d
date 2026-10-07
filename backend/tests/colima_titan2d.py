# Executed by the official Titan2D 4.2.0 embedded Python 2.7 interpreter.
# Keep syntax compatible with Python 2.7; TitanSimulation is injected by titan.
sim = TitanSimulation(overwrite_output=True)  # noqa: F821
sim.setGIS(gis_format="GDAL", gis_map="/dem/colimafinemini.tif")
sim.setScale(length_scale=4000.0, gravity_scale=9.8)
sim.setNumProp(AMR=True, number_of_cells_across_axis=16, order="First")
sim.setMatModel(model="Coulomb", int_frict=37.0, bed_frict=27.0)
sim.addPile(
    pile_type="Cylinder",
    height=30.0,
    center=[644956.0, 2157970.0],
    radii=[55.0, 55.0],
    orientation=0.0,
    Vmagnitude=0.0,
    Vdirection=0.0,
)
sim.setTimeProps(max_iter=100000, max_time=150.0)
sim.setRestartOutput(enabled=False)
sim.setTimeSeriesOutput(vizoutput="xdmf", dtime=1.0)
sim.run()
