"""Extract official Titan2D XDMF/HDF5 leaf cells and plot Colima comparisons.

Run from backend: uv run --with h5py --with seaborn --with matplotlib python
tests/colima_report.py
"""

import re
import json
import hashlib
import argparse
import xml.etree.ElementTree as ET

import matplotlib


matplotlib.use("Agg")
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from colima_comparison import (
    CENTER,
    OUTPUT,
    ANALYTIC_VOLUME,
    load_grid,
    depth_metrics,
    rasterize_cells,
    read_adaptive_state,
)
from matplotlib.colors import LightSource


def extract_reference():
    directory = OUTPUT / "titan2d"
    xml = ET.parse(directory / "vizout_xdmf_p0000.xmf")
    elements = xml.findall(".//Grid[Time]")
    grid = load_grid(5)
    envelope = np.zeros_like(grid.b)
    stats = []
    for element in elements:
        t = float(element.find("Time").attrib["Value"])
        # Titan2D also writes at its default iteration interval; use only the
        # common integer-second states so maximum depth has identical sampling.
        if abs(t - round(t)) > 1e-6 or t < 0 or t > 150:
            continue
        bounds, area, h, hu, hv = read_adaptive_state(element, directory)
        centers = (bounds[:, :2] + bounds[:, 2:]) / 2
        wet = h > 0.1
        speed = np.divide(np.hypot(hu, hv), h, out=np.zeros_like(h), where=wet)
        raster = rasterize_cells(bounds, h, grid)
        volume = float(np.sum(h * area))
        # Domain is identical and all retained wet cells should fit inside it.
        if not np.isclose(raster.sum() * grid.dx**2, volume, rtol=1e-8, atol=1e-4):
            raise ValueError(
                "Conservative rasterization failed or state is outside DEM"
            )
        np.maximum(envelope, raster, out=envelope)
        stats.append(
            {
                "t": t,
                "volume_m3": volume,
                "umax": float(speed.max()),
                "runout": float(np.hypot(*(centers[wet] - CENTER).T).max())
                if wet.any()
                else 0,
                "area": float(area[wet].sum() / 1e6),
                "hmax": float(h.max()),
                "cells": len(h),
                "min_cell_m": float(np.sqrt(area).min()),
                "max_wet_cell_m": float(np.sqrt(area[wet]).max()) if wet.any() else 0,
            }
        )
        if round(t) % 20 == 0:
            print(f"Extracted Titan2D t={t:g}, cells={len(h)}", flush=True)
    times = np.array([s["t"] for s in stats])
    if not np.allclose(times, np.arange(151), atol=1e-6):
        raise ValueError(
            f"Expected 151 shared states from 0 to 150 s; got {len(times)}"
        )
    np.savez_compressed(
        directory / "comparison.npz", saved_h_max=envelope, final_h=raster
    )
    (directory / "state_stats.json").write_text(json.dumps(stats, indent=2))
    return stats, envelope, raster


def main(reuse_reference=False):
    if reuse_reference:
        reference_stats = json.loads((OUTPUT / "titan2d/state_stats.json").read_text())
        with np.load(OUTPUT / "titan2d/comparison.npz") as z:
            reference, final_reference = z["saved_h_max"], z["final_h"]
    else:
        reference_stats, reference, final_reference = extract_reference()
    grid = load_grid(5)
    series = []
    for row in reference_stats:
        series.append(
            dict(
                row,
                model="Titan2D",
                volume_percent=100 * row["volume_m3"] / ANALYTIC_VOLUME,
            )
        )
    comparison = {}
    for dx in (2.5, 5, 10):
        directory = OUTPUT / f"titan3d-{dx}m"
        manifest = json.loads((directory / "manifest.json").read_text())
        stats = json.loads((directory / "stats.json").read_text())
        if not np.allclose(
            [s["t"] for s in stats], [s["t"] for s in reference_stats], atol=1e-6
        ):
            raise ValueError("Simulation times differ")
        for row in stats:
            volume = row["vol"] * row["released_m3"]
            series.append(
                dict(
                    row,
                    model=f"titan3d {dx} m",
                    volume_m3=volume,
                    volume_percent=100 * volume / ANALYTIC_VOLUME,
                )
            )
        with np.load(directory / "maxima.npz") as z:
            candidate = z["saved_h_max"]
        with np.load(directory / "frame-0150.npz") as z:
            final = z["h"].astype(float)
        if dx == 10:
            # Exact overlap for nested 10 m cells on the common 5 m raster.
            candidate = np.repeat(np.repeat(candidate, 2, axis=0), 2, axis=1)
            final = np.repeat(np.repeat(final, 2, axis=0), 2, axis=1)
        elif dx == 2.5:
            # Rasterize each saved state before taking the time maximum, just
            # as for Titan2D. Averaging native maxima would change that order.
            candidate = np.zeros_like(grid.b)
            for k in range(len(stats)):
                with np.load(directory / f"frame-{k:04d}.npz") as z:
                    sampled = (
                        z["h"]
                        .reshape(grid.ny, 2, grid.nx, 2)
                        .mean(axis=(1, 3), dtype=np.float64)
                    )
                    np.maximum(candidate, sampled, out=candidate)
            final = final.reshape(grid.ny, 2, grid.nx, 2).mean(axis=(1, 3))
        comparison[str(dx)] = {
            "maximum_depth": depth_metrics(reference, candidate, 5),
            "final_depth": depth_metrics(final_reference, final, 5),
            "final_runout_relative_error": (
                stats[-1]["runout"] / reference_stats[-1]["runout"]
            )
            - 1,
            "peak_speed_relative_error": max(s["umax"] for s in stats)
            / max(s["umax"] for s in reference_stats)
            - 1,
            "initial_volume_percent_analytic": 100
            * manifest["initial_volume_m3"]
            / ANALYTIC_VOLUME,
            "volume_balance_relative_error": stats[-1]["vol"]
            + stats[-1]["vol_out"]
            - 1,
            "final_runout_m": stats[-1]["runout"],
            "peak_speed_m_s": max(s["umax"] for s in stats),
            "wall_time_s": manifest["wall_time_s"],
            "maximum_mass_balance_relative_error": max(
                abs(s["vol"] + s["vol_out"] - 1) for s in stats
            ),
            "runout_time_series_rmse_m": float(
                np.sqrt(
                    np.mean(
                        (
                            np.array([s["runout"] for s in stats])
                            - np.array([s["runout"] for s in reference_stats])
                        )
                        ** 2
                    )
                )
            ),
            "speed_time_series_rmse_m_s": float(
                np.sqrt(
                    np.mean(
                        (
                            np.array([s["umax"] for s in stats])
                            - np.array([s["umax"] for s in reference_stats])
                        )
                        ** 2
                    )
                )
            ),
        }
        if dx == 5:
            candidate_5m = candidate
    frame = pd.DataFrame(series)
    frame.to_csv(OUTPUT / "time_series.csv", index=False)
    # Exploratory screening criteria, not a claim of physical equivalence.
    primary = comparison["5"]
    checks = {
        "final_runout_within_10_percent": abs(primary["final_runout_relative_error"])
        <= 0.1,
        "peak_speed_within_20_percent": abs(primary["peak_speed_relative_error"])
        <= 0.2,
        "maximum_footprint_iou_at_least_0_70": primary["maximum_depth"]["footprint_iou"]
        >= 0.70,
        "titan3d_mass_balance_within_0_1_percent": abs(
            primary["maximum_mass_balance_relative_error"]
        )
        <= 0.001,
    }
    result = {
        "comparison": comparison,
        "screening_checks": checks,
        "reference_final_runout_m": reference_stats[-1]["runout"],
        "reference_peak_speed_m_s": max(s["umax"] for s in reference_stats),
        "reference_initial_volume_percent_analytic": 100
        * reference_stats[0]["volume_m3"]
        / ANALYTIC_VOLUME,
        "reference_final_volume_percent_initial": 100
        * reference_stats[-1]["volume_m3"]
        / reference_stats[0]["volume_m3"],
        "reference_cell_size_min_m": min(s["min_cell_m"] for s in reference_stats),
        "binary_archive_sha256": hashlib.sha256(
            (OUTPUT / "toolchain/titan2d-v4.2.0-Linux-64bit.tar.gz").read_bytes()
        ).hexdigest(),
        "titan2d_input_sha256": hashlib.sha256(
            (OUTPUT / "titan2d/input.py").read_bytes()
        ).hexdigest(),
        "reference_times": [s["t"] for s in reference_stats],
        "reference_discrete_mass_drift_percent": 100
        * (reference_stats[-1]["volume_m3"] / reference_stats[0]["volume_m3"] - 1),
        "plotting_versions": {
            "matplotlib": matplotlib.__version__,
            "seaborn": sns.__version__,
            "pandas": pd.__version__,
        },
    }
    (OUTPUT / "metrics.json").write_text(json.dumps(result, indent=2))
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.2)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    palette = {
        "titan3d 2.5 m": "#419558",
        "Titan2D": "#1875b9",
        "titan3d 5 m": "#f27915",
        "titan3d 10 m": "#6f6f6f",
    }
    for ax, metric, label in zip(
        axes,
        ["umax", "runout", "volume_percent"],
        [
            "Maximum speed, h > 0.1 m [m/s]",
            "Front distance, h > 0.1 m [m]",
            "Volume [% of analytic cylinder]",
        ],
        strict=True,
    ):
        sns.lineplot(
            data=frame,
            x="t",
            y=metric,
            hue="model",
            palette=palette,
            estimator=None,
            ax=ax,
        )
        ax.set(xlabel="Time [s]", ylabel=label)
    # Keep the upstream diagnostic visibly separate from integrated state mass.
    diagnostic = []
    for line in (OUTPUT / "titan2d/output_summary.-00001").read_text().splitlines():
        match = re.search(r"(\d+):(\d+):([\d.]+).*stat volume=([\d.eE+-]+)", line)
        if match:
            hr, minute, sec, vol = map(float, match.groups())
            diagnostic.append(
                (hr * 3600 + minute * 60 + sec, vol / ANALYTIC_VOLUME * 100)
            )
    if diagnostic:
        t, v = np.array(diagnostic).T
        axes[2].plot(
            t, v, ":", color=palette["Titan2D"], label="Titan2D log diagnostic"
        )
        axes[2].legend(fontsize=9)
    fig.suptitle("Colima Coulomb: shared 1 s saved states; matched cylinder release")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT / f"time-series.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(17, 6), sharex=True, sharey=True)
    extent = grid.bounds[0], grid.bounds[2], grid.bounds[1], grid.bounds[3]
    shade = LightSource(azdeg=315, altdeg=45).hillshade(np.flipud(grid.b), dx=5, dy=5)
    wet = (reference > 0.1) | (candidate_5m > 0.1)
    jj, ii = np.nonzero(wet)
    lim = (
        grid.x[ii.min()] - 200,
        grid.x[ii.max()] + 200,
        grid.y[jj.min()] - 200,
        grid.y[jj.max()] + 200,
    )
    vmax = max(1, float(np.percentile(np.r_[reference[wet], candidate_5m[wet]], 99.5)))
    for ax in axes:
        ax.imshow(shade, origin="upper", extent=extent, cmap="gray", vmin=0, vmax=1)
        ax.set(xlim=lim[:2], ylim=lim[2:], xlabel="Easting [m, UTM 13N]")
        ax.ticklabel_format(style="plain", useOffset=False)
        ax.grid(False)
    for ax, data, title in zip(
        axes[:2],
        [reference, candidate_5m],
        ["Titan2D 4.2.0 (AMR, first order)", "titan3d (5 m, MUSCL second order)"],
        strict=True,
    ):
        artist = ax.imshow(
            np.ma.masked_where(data <= 0.1, data),
            origin="lower",
            extent=extent,
            cmap="magma_r",
            vmin=0,
            vmax=vmax,
        )
        ax.contour(grid.x, grid.y, data, levels=[0.1], colors="black", linewidths=0.5)
        ax.scatter(*CENTER, marker="^", c="cyan", s=20)
        ax.set_title(title + "\nMaximum depth, shared states 0–150 s")
    fig.colorbar(
        artist, ax=list(axes[:2]), label="Maximum depth [m]", extend="max", shrink=0.85
    )
    difference = candidate_5m - reference
    bound = max(0.1, float(np.percentile(np.abs(difference[wet]), 99)))
    diff_artist = axes[2].imshow(
        np.ma.masked_where(~wet, difference),
        origin="lower",
        extent=extent,
        cmap="RdBu_r",
        vmin=-bound,
        vmax=bound,
    )
    axes[2].contour(
        grid.x, grid.y, reference, levels=[0.1], colors="black", linewidths=0.5
    )
    axes[2].contour(
        grid.x, grid.y, candidate_5m, levels=[0.1], colors="#f27915", linewidths=0.5
    )
    axes[2].set_title(
        "Difference titan3d − Titan2D\nBlack: Titan2D 0.1 m; orange: titan3d"
    )
    axes[0].set_ylabel("Northing [m]")
    fig.colorbar(
        diff_artist, ax=axes[2], label="Δ maximum depth [m]", extend="both", shrink=0.85
    )
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT / f"maximum-depth.{ext}", dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(result, indent=2))
    return checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reuse-reference",
        action="store_true",
        help="Reuse previously extracted reference files; do not rerun Titan2D between extraction and reuse.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if any primary 5 m screening criterion fails.",
    )
    args = parser.parse_args()
    checks = main(args.reuse_reference)
    if args.check and not all(checks.values()):
        raise SystemExit(1)
