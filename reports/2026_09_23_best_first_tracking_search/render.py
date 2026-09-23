#!/usr/bin/env python3
"""Render the qualified best-first benchmark."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
CITIES = {"sacramento": (38.5816, -121.4944), "reno": (39.5296, -119.8138)}


def reference_offset(latitude, longitude, center):
    """Invert the search's spherical azimuthal-equidistant coordinates."""
    lat, lon, lat0, lon0 = map(math.radians, (latitude, longitude, *center))
    dl = lon - lon0
    east = math.cos(lat) * math.sin(dl)
    north = math.cos(lat0) * math.sin(lat) - math.sin(lat0) * math.cos(lat) * math.cos(dl)
    dot = math.sin(lat0) * math.sin(lat) + math.cos(lat0) * math.cos(lat) * math.cos(dl)
    norm = math.hypot(east, north)
    scale = 6371.0088 * math.atan2(norm, dot) / norm if norm else 0.0
    return east * scale, north * scale


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def incumbent(trace):
    count, best, output = 0, None, []
    for event in trace:
        if event.get("event") != "evaluate":
            continue
        count += 1
        value = event["weighted_mse_hz2"] ** 0.5
        best = value if best is None else min(best, value)
        output.append((count, best))
    return output


def main():
    summary = read(HERE / "summary.json")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, city in zip(axes, ("sacramento", "reno"), strict=True):
        for row in (item for item in summary["rows"] if item["city"] == city):
            progress = incumbent(row["trace"])
            ax.plot(
                [item[0] for item in progress],
                [item[1] for item in progress],
                label=row["priority_mode"],
            )
        ax.set(
            title=city.title(),
            xlabel="Full point evaluations",
            ylabel="Best capped weighted RMSE (Hz)",
        )
        ax.grid(alpha=0.2)
        ax.legend()
    fig.savefig(HERE / "best-cost-vs-evaluations.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    modes = ("exact-centre", "parent-linear")
    for ax, city in zip(axes, ("sacramento", "reno"), strict=True):
        selected = [
            next(
                row
                for row in summary["rows"]
                if row["city"] == city and row["priority_mode"] == mode
            )
            for mode in modes
        ]
        ax.bar(modes, [row["search_s"] for row in selected])
        ax.set(title=city.title(), ylabel="Search seconds")
    fig.savefig(HERE / "runtime.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    zoom_fig, zoom_axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    reference = read(HERE / "inputs" / "evaluation-reference.json")
    for ax, city in zip(axes, ("sacramento", "reno"), strict=True):
        row = next(
            item
            for item in summary["rows"]
            if item["city"] == city and item["priority_mode"] == "exact-centre"
        )
        events = [event for event in row["trace"] if event.get("event") == "evaluate"]
        plot = ax.scatter(
            [event["east_km"] for event in events],
            [event["north_km"] for event in events],
            c=[event["weighted_mse_hz2"] ** 0.5 for event in events],
            s=14,
            cmap="viridis_r",
        )
        selected = row["selected"]
        ax.scatter(
            selected["east_km"],
            selected["north_km"],
            marker="*",
            s=170,
            color="red",
            edgecolor="black",
            label="selected 12.5 km cell",
        )
        truth_e, truth_n = reference_offset(
            reference["latitude_deg"], reference["longitude_deg"], CITIES[city]
        )
        zoom_ax = zoom_axes[0 if city == "sacramento" else 1]
        zoom_plot = zoom_ax.scatter(
            [event["east_km"] for event in events],
            [event["north_km"] for event in events],
            c=[event["weighted_mse_hz2"] ** 0.5 for event in events],
            s=30, cmap="viridis_r", norm=plot.norm,
        )
        zoom_ax.scatter(selected["east_km"], selected["north_km"], marker="*",
                        s=170, color="red", edgecolor="black", zorder=5,
                        label="selected 12.5 km cell")
        for target in (ax, zoom_ax):
            target.scatter(truth_e, truth_n, marker="+", s=220, color="black",
                           linewidths=2.2, zorder=6, label="true Sausalito reference")
            target.plot([selected["east_km"], truth_e], [selected["north_km"], truth_n],
                        color="black", linestyle="--", linewidth=1, zorder=4)
        zoom_ax.set(xlim=(truth_e - 30, truth_e + 30), ylim=(truth_n - 30, truth_n + 30),
                    title=f"{city.title()} · error {row['postselection_distance_km']:.2f} km",
                    xlabel="East of prior center (km)", ylabel="North of prior center (km)",
                    aspect="equal")
        zoom_ax.grid(alpha=0.2)
        zoom_ax.legend(fontsize=8)
        zoom_fig.colorbar(zoom_plot, ax=zoom_ax, label="Capped weighted RMSE (Hz)")
        circle = plt.Circle((0, 0), 500, fill=False, color="black", linewidth=0.8)
        ax.add_patch(circle)
        ax.set(title=city.title(), xlabel="East (km)", ylabel="North (km)", aspect="equal")
        ax.legend(fontsize=8)
        fig.colorbar(plot, ax=ax, label="Capped weighted RMSE (Hz)")
    fig.savefig(HERE / "visited-points.png", dpi=180)
    plt.close(fig)
    zoom_fig.suptitle("True reference overlaid after search; not used for inference")
    zoom_fig.savefig(HERE / "visited-points-closeup.png", dpi=180)
    plt.close(zoom_fig)

    files = {}
    for path in sorted(HERE.rglob("*")):
        if (
            path.is_file()
            and path.name != "artifact-manifest.json"
            and "__pycache__" not in path.parts
        ):
            files[str(path.relative_to(HERE))] = {
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            }
    (HERE / "artifact-manifest.json").write_text(
        json.dumps({"schema": "report-artifact-manifest/v1", "files": files}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
