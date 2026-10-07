import numpy as np, rasterio
from titan3d.core.grid import Grid
from titan3d.core.params import FlowParams
from titan3d.core.solver import Solver
from titan3d.core.numerics import velocity
import os
src=rasterio.open(os.environ.get("COLIMA_DEM", "colimafinemini.geotiff"))
b=np.ascontiguousarray(src.read(1).astype(float)[::-1]); dx=5.0
g=Grid(b=b,dx=dx,x0=src.bounds.left+2.5,y0=src.bounds.bottom+2.5,crs="EPSG:32613")
X,Y=np.meshgrid(g.x,g.y); h0=np.where((X-644956)**2+(Y-2157970)**2<=55**2,30.0,0.0)
p=FlowParams(phi_bed_deg=27,phi_int_deg=37); s=Solver(g,p); st=s.initial_state(h0)
sy,sx=np.gradient(b,dx); slope=np.degrees(np.arctan(np.hypot(sx,sy)))
for st in s.run(st,150,25):
    sp=velocity(st.h,np.hypot(st.hu,st.hv),p.h_dry); j,i=np.unravel_index(sp.argmax(),sp.shape)
    mov=(sp>1)&(st.h>p.h_dry)
    print(f"t={st.t:5.0f} umax={sp.max():5.1f} at E{g.x[i]:.0f} N{g.y[j]:.0f} h={st.h[j,i]:.4f} m slope={slope[j,i]:.1f}deg | cells moving>1m/s {mov.sum()}, their volume {st.h[mov].sum()*dx*dx:.1f} m3, max h {st.h[mov].max() if mov.any() else 0:.3f}")
