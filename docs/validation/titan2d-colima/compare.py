"""Compare Titan2D and titan3d on the colimafinemini Coulomb example.

Usage: uv run --with matplotlib --with h5py python compare.py T2D_RUN_DIR T3D_DIR [T3D_DIR_10M] OUT_DIR
"""
import re, sys, json, glob
from pathlib import Path
import numpy as np
import h5py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

XC, YC = 644956.0, 2157970.0
T2D, T3D, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[-1])
T3D10 = Path(sys.argv[3]) if len(sys.argv) == 5 else None
OUT.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ Titan2D
def read_grid(path):
    """pileheightrecord / maxkerecord: header Nx, X range, Ny, Y range; rows south→north."""
    lines = open(path).read().splitlines()
    nx, x0, x1 = re.findall(r"Nx=(\d+): X=\{\s*([-\d.eE+]+),\s*([-\d.eE+]+)\}", lines[0])[0]
    ny, y0, y1 = re.findall(r"Ny=(\d+): Y=\{\s*([-\d.eE+]+),\s*([-\d.eE+]+)\}", lines[1])[0]
    nx, ny, x0, x1, y0, y1 = int(nx), int(ny), float(x0), float(x1), float(y0), float(y1)
    a = np.array([[float(v) for v in ln.split()] for ln in lines[3:3 + ny]])
    dx, dy = (x1 - x0) / nx, (y1 - y0) / ny
    x = x0 + dx * (np.arange(nx) + 0.5)
    y = y0 + dy * (np.arange(ny) + 0.5)
    return a, x, y, dx, dy


def read_log(path):
    txt = open(path).read()
    pat = re.compile(r"time step (\d+) the time is (\d+):(\d+):([\d.]+).*?volume is ([\d.eE+]+).*?"
                     r"max height is ([\d.eE+]+).*?max velocity is ([\d.eE+]+)", re.S)
    rows = [(int(s), int(h) * 3600 + int(m) * 60 + float(sec), float(v), float(hm), float(um))
            for s, h, m, sec, v, hm, um in pat.findall(txt)]
    return np.array(rows)


def t2d_snapshot(h5):
    f = h5py.File(h5, "r")
    P, C = f["Mesh/Points"][:], f["Mesh/Connections"][:]
    h = f["Properties/PILE_HEIGHT"][:, 0]
    q = P[C]
    xc, yc = q[:, :, 0].mean(1), q[:, :, 1].mean(1)
    area = (q[:, :, 0].max(1) - q[:, :, 0].min(1)) * (q[:, :, 1].max(1) - q[:, :, 1].min(1))
    return xc, yc, h, area


def times_of_h5(xmf):
    txt = open(xmf).read()
    ts = [float(t) for t in re.findall(r'<Time Value="([\d.eE+-]+)"', txt)]
    files = re.findall(r"(vizout/\S+\.h5):/Mesh/Points", txt)
    return list(zip(ts, files))


ph_file = sorted(glob.glob(str(T2D / "pileheightrecord.*")))[0]
t2_hmax, gx, gy, gdx, gdy = read_grid(ph_file)
log = read_log(T2D / "run.log")
snaps = times_of_h5(T2D / "vizout_xdmf_p0000.xmf")

# ------------------------------------------------------------------ titan3d
def load_t3d(d):
    r = np.load(d / "result.npz")
    s = json.load(open(d / "summary.json"))
    return r, s

r3, s3 = load_t3d(T3D)
x3, y3, b3 = r3["x"], r3["y"], r3["b"]


def sample(field, fx, fy, tx, ty):
    """Nearest-cell sample of a regular field (fx, fy cell centres) at points tx, ty."""
    ddx = fx[1] - fx[0]
    i = np.clip(np.round((tx - fx[0]) / ddx).astype(int), 0, fx.size - 1)
    j = np.clip(np.round((ty - fy[0]) / ddx).astype(int), 0, fy.size - 1)
    return field[j, i]


GX, GY = np.meshgrid(gx, gy)
t3_on_g = sample(r3["h_max"], x3, y3, GX, GY)     # titan3d max depth on Titan2D's outline grid
bed_on_g = sample(b3, x3, y3, GX, GY)
cell_a = gdx * gdy
R = np.hypot(GX - XC, GY - YC)
z_src = float(sample(b3, x3, y3, np.array([XC]), np.array([YC]))[0])


def footprint_metrics(hm, thr):
    w = hm > thr
    if not w.any():
        return dict(area_km2=0, runout_m=0, HL=np.nan)
    k = np.argmax(np.where(w, R, -1))
    L = R.flat[k]
    return dict(area_km2=w.sum() * cell_a / 1e6, runout_m=float(L),
                HL=float((z_src - bed_on_g.flat[k]) / L) if L > 0 else np.nan,
                front_xy=(float(GX.flat[k]), float(GY.flat[k])), front_z=float(bed_on_g.flat[k]))


rows = []
for thr in (0.1, 0.5, 1.0):
    a, b = t2_hmax > thr, t3_on_g > thr
    inter, union = (a & b).sum(), (a | b).sum()
    m2, m3 = footprint_metrics(t2_hmax, thr), footprint_metrics(t3_on_g, thr)
    rows.append(dict(thr=thr, t2=m2, t3=m3, jaccard=inter / union if union else np.nan,
                     t2_only_km2=(a & ~b).sum() * cell_a / 1e6, t3_only_km2=(b & ~a).sum() * cell_a / 1e6))

# final deposit
t_last, f_last = snaps[-1]
xc, yc, h2f, a2 = t2d_snapshot(T2D / f_last)
def deposit_stats(xs, ys, h, a):
    w = h > 0.1
    V = (h * a).sum()
    cx, cy = (h * a * xs).sum() / V, (h * a * ys).sum() / V
    return dict(volume_m3=float(V), centroid=(float(cx), float(cy)),
                centroid_dist_m=float(np.hypot(cx - XC, cy - YC)), hmax=float(h.max()))
X3, Y3 = np.meshgrid(x3, y3)
dep2 = deposit_stats(xc, yc, h2f, a2)
dep3 = deposit_stats(X3.ravel(), Y3.ravel(), r3["h_final"].ravel().astype(float), np.full(X3.size, s3["dx"] ** 2))
dep2["t"] = t_last; dep3["t"] = s3["ts"][-1]["t"]

# per-snapshot front distance (Titan2D h5 vs titan3d frames)
fronts, t2vol = [], []
for k, (t, f) in enumerate(snaps):
    xs, ys, hh, aa = t2d_snapshot(T2D / f)
    t2vol.append((t, float((hh * aa).sum())))
    w = hh > 0.1
    L2 = float(np.hypot(xs[w] - XC, ys[w] - YC).max()) if w.any() else 0.0
    idx = int(round(t / s3["params"]["every"]))
    L3 = s3["ts"][idx]["runout_m"] if idx < len(s3["ts"]) else np.nan
    fronts.append((t, L2, L3))
fronts = np.array(fronts)
t2vol = np.array(t2vol)

summary = dict(
    titan2d=dict(pile_volume_analytic=285099.5, v_initial_mesh=float(log[0, 2]), v_final=float(log[-1, 2]),
                 t_final=float(log[-1, 1]), steps=int(log[-1, 0]), outline_grid=[len(gx), len(gy), gdx, gdy],
                 umax_peak=float(log[:, 4].max()), hmax_final=float(log[-1, 3])),
    titan3d=dict(v0=s3["v0"], v_final=s3["ts"][-1]["vol"], dx=s3["dx"], steps=s3["ts"][-1]["steps"],
                 wall_s=s3["ts"][-1]["wall_s"], umax_peak=max(e["umax"] for e in s3["ts"]),
                 hmax_final=s3["ts"][-1]["hmax"]),
    footprints=rows, deposit=dict(titan2d=dep2, titan3d=dep3), z_src=z_src,
    fronts=fronts.tolist(), titan2d_state_volume=t2vol.tolist(),
)
if T3D10:
    r10, s10 = load_t3d(T3D10)
    h10 = sample(r10["h_max"], r10["x"], r10["y"], GX, GY)
    summary["titan3d_10m"] = {f"thr{thr}": footprint_metrics(h10, thr) for thr in (0.1, 0.5, 1.0)}
    summary["titan3d_10m"]["jaccard_vs_5m_0.1"] = float(((h10 > .1) & (t3_on_g > .1)).sum() / ((h10 > .1) | (t3_on_g > .1)).sum())
    summary["titan3d_10m"]["wall_s"] = s10["ts"][-1]["wall_s"]
json.dump(summary, open(OUT / "metrics.json", "w"), indent=1, default=float)

# ------------------------------------------------------------------ figures
ls = LightSource(azdeg=315, altdeg=45)
shade = ls.hillshade(b3, vert_exag=1, dx=s3["dx"], dy=s3["dx"])
ext3 = [x3[0] - s3["dx"] / 2, x3[-1] + s3["dx"] / 2, y3[0] - s3["dx"] / 2, y3[-1] + s3["dx"] / 2]
extg = [gx[0] - gdx / 2, gx[-1] + gdx / 2, gy[0] - gdy / 2, gy[-1] + gdy / 2]
w = np.where((t2_hmax > .1) | (t3_on_g > .1))
pad = 250
zoom = [GX[w].min() - pad, GX[w].max() + pad, GY[w].min() - pad, GY[w].max() + pad]
vmax = float(np.nanpercentile(np.r_[t2_hmax[t2_hmax > .1], t3_on_g[t3_on_g > .1]], 99))

fig, axs = plt.subplots(1, 3, figsize=(16, 6.2), constrained_layout=True)
for ax, data, title in [(axs[0], t2_hmax, "Titan2D 4.2.0 (AMR, 1st order)"),
                        (axs[1], t3_on_g, f"titan3d ({s3['dx']:.0f} m, MUSCL 2nd order)")]:
    ax.imshow(shade, extent=ext3, origin="lower", cmap="gray", vmin=0, vmax=1)
    im = ax.imshow(np.ma.masked_less(data, 0.1), extent=extg, origin="lower", cmap="magma_r", vmin=0, vmax=vmax)
    ax.contour(GX, GY, data, levels=[0.1], colors="k", linewidths=0.6)
    ax.plot(XC, YC, "c^", ms=7, mec="k")
    ax.set_title(f"{title}\nmax flow depth over 0–{summary['titan2d']['t_final']:.0f} s", fontsize=10)
fig.colorbar(im, ax=axs[:2], shrink=0.8, label="max flow depth [m]")
d = t3_on_g - t2_hmax
mask = (t2_hmax > .1) | (t3_on_g > .1)
lim = float(np.nanpercentile(np.abs(d[mask]), 98))
axs[2].imshow(shade, extent=ext3, origin="lower", cmap="gray", vmin=0, vmax=1)
im2 = axs[2].imshow(np.ma.masked_where(~mask, d), extent=extg, origin="lower", cmap="RdBu_r", vmin=-lim, vmax=lim)
axs[2].contour(GX, GY, t2_hmax, levels=[0.1], colors="k", linewidths=0.6)
axs[2].contour(GX, GY, t3_on_g, levels=[0.1], colors="tab:orange", linewidths=0.8)
axs[2].set_title("difference titan3d − Titan2D [m]\nblack: Titan2D 0.1 m outline · orange: titan3d", fontsize=10)
fig.colorbar(im2, ax=axs[2], shrink=0.8, label="Δ max depth [m]")
for ax in axs:
    ax.set_xlim(zoom[:2]); ax.set_ylim(zoom[2:]); ax.set_aspect("equal")
    ax.set_xlabel("Easting [m, UTM 13N]"); ax.ticklabel_format(useOffset=False, style="plain")
axs[0].set_ylabel("Northing [m]")
fig.savefig(OUT / "max_depth_maps.png", dpi=130)

fig, axs = plt.subplots(1, 3, figsize=(16, 4.2), constrained_layout=True)
t3t = np.array([e["t"] for e in s3["ts"]])
axs[0].plot(log[:, 1], log[:, 4], lw=1, label="Titan2D"); axs[0].plot(t3t, [e["umax"] for e in s3["ts"]], "o-", ms=3, label="titan3d")
axs[0].set_ylabel("max speed [m/s]")
axs[1].plot(fronts[:, 0], fronts[:, 1], "o-", ms=3, label="Titan2D"); axs[1].plot(fronts[:, 0], fronts[:, 2], "o-", ms=3, label="titan3d")
axs[1].set_ylabel("front distance from pile [m] (h > 0.1 m)")
axs[2].plot(t2vol[:, 0], t2vol[:, 1] / 285099.5 * 100, "o-", ms=3, label="Titan2D (sum of saved state)")
axs[2].plot(log[:, 1], log[:, 2] / 285099.5 * 100, ":", lw=1, color="tab:blue", label="Titan2D log 'volume' diagnostic"); axs[2].plot(t3t, np.array([e["vol"] for e in s3["ts"]]) / 285099.5 * 100, "o-", ms=3, label="titan3d")
axs[2].set_ylabel("volume [% of analytic pile]")
for ax in axs:
    ax.set_xlabel("time [s]"); ax.grid(alpha=.3); ax.legend()
fig.savefig(OUT / "time_series.png", dpi=130)
print(json.dumps(summary, indent=1, default=float)[:4000])
