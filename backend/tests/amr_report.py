"""Extract fresh Titan2D leaves; compare AMR, uniform fine and upstream runs."""

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
from amr_colima import OUTPUT
from colima_comparison import (
    ROOT,
    CENTER,
    ANALYTIC_VOLUME,
    load_grid,
    depth_metrics,
    rasterize_cells,
    read_adaptive_state,
)
from matplotlib.colors import LightSource


def extract_reference():
    directory = OUTPUT / "titan2d"
    elements = ET.parse(directory / "vizout_xdmf_p0000.xmf").findall(".//Grid[Time]")
    grid = load_grid(5)
    envelope = np.zeros_like(grid.b)
    rows = []
    for element in elements:
        t = float(element.find("Time").attrib["Value"])
        if t < 0 or t > 150 or abs(t - round(t)) > 1e-6:
            continue
        bounds, area, h, qx, qy = read_adaptive_state(element, directory)
        centers = (bounds[:, :2] + bounds[:, 2:]) / 2
        wet = h > 0.1
        speed = np.divide(np.hypot(qx, qy), h, out=np.zeros_like(h), where=wet)
        raster = rasterize_cells(bounds, h, grid)
        volume = float(np.dot(h, area))
        if not np.isclose(raster.sum() * 25, volume, rtol=1e-8, atol=1e-4):
            raise ValueError("Reference raster transfer does not conserve volume")
        np.maximum(envelope, raster, out=envelope)
        rows.append(
            {
                "t": t,
                "umax": float(speed.max()),
                "runout": float(np.hypot(*(centers[wet] - CENTER).T).max())
                if wet.any()
                else 0,
                "area": float(area[wet].sum() / 1e6),
                "volume_m3": volume,
                "leaf_cells": len(h),
                "min_dx_m": float(np.sqrt(area).min()),
            }
        )
    if len(rows) != 151 or not np.allclose(
        [r["t"] for r in rows], np.arange(151), atol=1e-6
    ):
        raise ValueError("Expected all 151 reference states at shared integer seconds")
    np.savez_compressed(
        directory / "comparison.npz", saved_h_max=envelope, final_h=raster
    )
    (directory / "state_stats.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    return rows, envelope, raster


def comparisons(reference, candidate, ref_rows, rows, native_candidate=False):
    metrics = depth_metrics(reference, candidate, 5)
    runout_key = "native_runout" if native_candidate else "runout"
    speed_key = "native_umax" if native_candidate else "umax"
    runout = rows[-1][runout_key] / ref_rows[-1]["runout"] - 1
    speed = max(r[speed_key] for r in rows) / max(r["umax"] for r in ref_rows) - 1
    return {
        "maximum_depth": metrics,
        "final_runout_relative_error": runout,
        "peak_speed_relative_error": speed,
        "final_runout_m": rows[-1][runout_key],
        "peak_speed_m_s": max(r[speed_key] for r in rows),
    }


def main(reuse_reference=False):
    if reuse_reference:
        ref_rows = json.loads((OUTPUT / "titan2d/state_stats.json").read_text())
        with np.load(OUTPUT / "titan2d/comparison.npz") as z:
            reference, final_reference = z["saved_h_max"], z["final_h"]
    else:
        ref_rows, reference, final_reference = extract_reference()
    series = [
        dict(r, model="Titan2D", volume_percent=100 * r["volume_m3"] / ANALYTIC_VOLUME)
        for r in ref_rows
    ]
    data = {}
    for model in ("uniform", "amr"):
        directory = OUTPUT / f"{model}-5m"
        rows = json.loads((directory / "stats.json").read_text())
        manifest = json.loads((directory / "manifest.json").read_text())
        if len(rows) != 151 or not np.allclose(
            [r["t"] for r in rows], np.arange(151), atol=1e-6
        ):
            raise ValueError("Candidate must have 151 matched states")
        with np.load(directory / "maxima.npz") as z:
            maximum = z["saved_h_max"]
        with np.load(directory / "frame-0150.npz") as z:
            final = z["h"]
        series.extend(
            dict(
                r,
                model="titan3d AMR 5–10 m" if model == "amr" else "titan3d uniform 5 m",
                volume_percent=100 * r["vol"] * r["released_m3"] / ANALYTIC_VOLUME,
            )
            for r in rows
        )
        data[model] = {
            "rows": rows,
            "manifest": manifest,
            "maximum": maximum,
            "final": final,
        }
    a, b = data["amr"], data["uniform"]
    vs_uniform = comparisons(b["maximum"], a["maximum"], b["rows"], a["rows"])
    vs_uniform["final_depth"] = depth_metrics(b["final"], a["final"], 5)
    vs_titan2d = comparisons(reference, a["maximum"], ref_rows, a["rows"], native_candidate=True)
    vs_titan2d["final_depth"] = depth_metrics(final_reference, a["final"], 5)
    budgets = {
        "uniform_footprint_iou_at_least_0.90": vs_uniform["maximum_depth"]["footprint_iou"]
        >= 0.9,
        "uniform_depth_rmse_at_most_0.25m": vs_uniform["maximum_depth"]["rmse_m"]
        <= 0.25,
        "uniform_final_runout_within_5percent": abs(
            vs_uniform["final_runout_relative_error"]
        )
        <= 0.05,
        "uniform_peak_speed_within_10percent": abs(
            vs_uniform["peak_speed_relative_error"]
        )
        <= 0.1,
        "mass_budget_within_0.1percent": a["manifest"]["max_mass_budget_relative_error"]
        <= 0.001,
    }
    screening = {
        "titan2d_footprint_iou_at_least_0.70": vs_titan2d["maximum_depth"]["footprint_iou"]
        >= 0.7,
        "titan2d_final_runout_within_10percent": abs(
            vs_titan2d["final_runout_relative_error"]
        )
        <= 0.1,
        "titan2d_peak_speed_within_20percent": abs(
            vs_titan2d["peak_speed_relative_error"]
        )
        <= 0.2,
    }
    archive = (
        ROOT
        / "backend/tests/out_colima_comparison/toolchain/titan2d-v4.2.0-Linux-64bit.tar.gz"
    )
    result = {
        "amr_vs_uniform": vs_uniform,
        "amr_vs_titan2d": vs_titan2d,
        "uniform_vs_titan2d": comparisons(reference, b["maximum"], ref_rows, b["rows"]),
        "amr_acceptance": budgets,
        "titan2d_screening": screening,
        "reference_final_runout_m": ref_rows[-1]["runout"],
        "reference_peak_speed_m_s": max(r["umax"] for r in ref_rows),
        "reference_mass_drift_relative": ref_rows[-1]["volume_m3"]
        / ref_rows[0]["volume_m3"]
        - 1,
        "reference_min_dx_m": min(r["min_dx_m"] for r in ref_rows),
        "runtime": {
            model: {
                k: v["manifest"][k]
                for k in (
                    "wall_time_s",
                    "warmup_s",
                    "process_peak_rss_mb",
                    "max_mass_budget_relative_error",
                )
            }
            for model, v in data.items()
        },
        "leaf_cells_min": min(r["leaf_cells"] for r in a["rows"]),
        "leaf_cells_max": max(r["leaf_cells"] for r in a["rows"]),
        "uniform_cells": int(np.prod(a["manifest"]["grid_shape"])),
        "regrids": a["rows"][-1]["regrids"],
        "provenance": {
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "titan2d_input_sha256": hashlib.sha256(
                (OUTPUT / "titan2d/input.py").read_bytes()
            ).hexdigest(),
            "run_manifests": {model: v["manifest"] for model, v in data.items()},
            "plotting_versions": {
                "matplotlib": matplotlib.__version__,
                "seaborn": sns.__version__,
                "pandas": pd.__version__,
            },
        },
    }
    (OUTPUT / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    frame = pd.DataFrame(series)
    frame.to_csv(OUTPUT / "time_series.csv", index=False)
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.1)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for ax, metric, label in zip(
        axes,
        ("umax", "runout", "volume_percent"),
        (
            "Maximum speed, h > 0.1 m [m/s]",
            "Front distance, h > 0.1 m [m]",
            "Integrated volume [% analytic cylinder]",
        ),
        strict=True,
    ):
        sns.lineplot(data=frame, x="t", y=metric, hue="model", estimator=None, ax=ax)
        ax.set(xlabel="Time [s]", ylabel=label)
    diagnostic = []
    for line in (OUTPUT / "titan2d/output_summary.-00001").read_text().splitlines():
        match = re.search(r"(\d+):(\d+):([\d.]+).*stat volume=([\d.eE+-]+)", line)
        if match:
            hour, minute, sec, vol = map(float, match.groups())
            diagnostic.append(
                (hour * 3600 + minute * 60 + sec, 100 * vol / ANALYTIC_VOLUME)
            )
    if diagnostic:
        t, vol = np.asarray(diagnostic).T
        axes[2].plot(t, vol, ":", label="Titan2D log diagnostic (separate)")
        axes[2].legend(fontsize=8)
    fig.suptitle(
        "Colima: fresh Titan2D, uniform fine-grid and experimental AMR; shared 1 s states"
    )
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT / f"time-series.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    g = load_grid(5)
    extent = (g.bounds[0], g.bounds[2], g.bounds[1], g.bounds[3])
    shade = LightSource(azdeg=315, altdeg=45).hillshade(np.flipud(g.b), dx=5, dy=5)
    wet_values = np.concatenate(
        [x[x > 0.1] for x in (reference, a["maximum"], b["maximum"])]
    )
    upper = np.percentile(wet_values, 99.5)
    delta = a["maximum"] - reference
    limit = max(
        np.percentile(np.abs(delta[(a["maximum"] > 0.1) | (reference > 0.1)]), 99), 0.1
    )
    fig, axes = plt.subplots(1, 4, figsize=(21, 6), sharex=True, sharey=True)
    for ax, values, title in zip(
        axes,
        (reference, b["maximum"], a["maximum"], delta),
        (
            "Titan2D 4.2.0 (first-order AMR)",
            "titan3d uniform 5 m",
            "titan3d AMR 5–10 m",
            "AMR minus Titan2D [m]",
        ),
        strict=True,
    ):
        ax.imshow(shade, cmap="gray", extent=extent)
        difference = ax is axes[3]
        visible = (
            ((reference > 0.1) | (a["maximum"] > 0.1)) if difference else values > 0.1
        )
        im = ax.imshow(
            np.flipud(np.ma.masked_where(~visible, values)),
            extent=extent,
            cmap="RdBu_r" if difference else "magma_r",
            vmin=-limit if difference else 0,
            vmax=limit if difference else upper,
        )
        ax.contour(g.x, g.y, reference, levels=[0.1], colors="black", linewidths=0.5)
        if difference:
            ax.contour(
                g.x,
                g.y,
                a["maximum"],
                levels=[0.1],
                colors="tab:orange",
                linewidths=0.5,
            )
        ax.set(title=title, xlabel="Easting [m, UTM 13N]")
        fig.colorbar(
            im,
            ax=ax,
            shrink=0.8,
            label="Δ max depth [m]" if difference else "Max depth [m]",
            extend="both" if difference else "max",
        )
    axes[0].set_ylabel("Northing [m]")
    axes[0].set_xlim(CENTER[0] - 2400, CENTER[0] + 500)
    axes[0].set_ylim(CENTER[1] - 2700, CENTER[1] + 500)
    fig.suptitle(
        "Colima sampled maximum flow depth, 0–150 s; black Titan2D / orange AMR 0.1 m outlines"
    )
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT / f"maximum-depth.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    subset = frame[frame.model != "Titan2D"]
    sns.lineplot(
        data=subset, x="t", y="leaf_cells", hue="model", estimator=None, ax=axes[0]
    )
    axes[0].axhline(
        result["uniform_cells"], color="gray", linestyle="--", label="Uniform cells"
    )
    axes[0].set(xlabel="Time [s]", ylabel="Computational leaf cells")
    timing = pd.DataFrame(
        [
            {"model": model, "seconds": v["wall_time_s"]}
            for model, v in result["runtime"].items()
        ]
    )
    sns.barplot(data=timing, x="model", y="seconds", ax=axes[1], errorbar=None)
    axes[1].set(ylabel="Run time incl. mesh and output [s]", xlabel="")
    fig.tight_layout()
    fig.savefig(OUTPUT / "mesh-cost.png", dpi=200)
    plt.close(fig)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "amr_vs_uniform",
                    "amr_vs_titan2d",
                    "amr_acceptance",
                    "titan2d_screening",
                    "runtime",
                )
            },
            indent=2,
        )
    )
    return all(budgets.values()), all(screening.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-reference", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="Fail if AMR release budgets fail"
    )
    parser.add_argument(
        "--check-titan2d",
        action="store_true",
        help="Also enforce upstream similarity screening",
    )
    args = parser.parse_args()
    adaptive_pass, reference_pass = main(args.reuse_reference)
    if (args.check and not adaptive_pass) or (
        args.check_titan2d and not reference_pass
    ):
        raise SystemExit(1)
