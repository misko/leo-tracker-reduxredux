#!/usr/bin/env python3
"""Render the frozen fine-resolution comparison."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
CITIES = {
    "sacramento": (38.5816, -121.4944),
    "reno": (39.5296, -119.8138),
}
LABELS = ("12.5 km / 400", "6.25 km / 400", "6.25 km / 800")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def truth_offset(city, reference):
    lat0, lon0 = map(math.radians, CITIES[city])
    lat, lon = map(math.radians, (reference["latitude_deg"], reference["longitude_deg"]))
    delta_lon = lon - lon0
    cosine = math.sin(lat0) * math.sin(lat) + math.cos(lat0) * math.cos(lat) * math.cos(delta_lon)
    angular = math.acos(max(-1.0, min(1.0, cosine)))
    bearing = math.atan2(
        math.sin(delta_lon) * math.cos(lat),
        math.cos(lat0) * math.sin(lat) - math.sin(lat0) * math.cos(lat) * math.cos(delta_lon),
    )
    distance = 6371.0088 * angular
    return distance * math.sin(bearing), distance * math.cos(bearing)


def evaluated(trace):
    return [event for event in trace if event.get("event") == "evaluate"]


def main():
    summary = read(HERE / "summary.json")
    reference = read(HERE / "inputs" / "evaluation-reference.json")
    rows = summary["rows"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, city in zip(axes, CITIES, strict=True):
        for label in LABELS:
            row = next(item for item in rows if item["city"] == city and item["label"] == label)
            best, progress = None, []
            for count, event in enumerate(evaluated(row["trace"]), 1):
                value = event["weighted_mse_hz2"] ** 0.5
                best = value if best is None else min(best, value)
                progress.append((count, best))
            ax.plot([x for x, _ in progress], [y for _, y in progress], label=label)
        ax.set(
            title=city.title(), xlabel="Evaluated points", ylabel="Best capped weighted RMSE (Hz)"
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(HERE / "cost-vs-evaluations.png", dpi=180)
    plt.close(fig)

    all_values = [
        event["weighted_mse_hz2"] ** 0.5 for row in rows for event in evaluated(row["trace"])
    ]
    shared_min, shared_max = min(all_values), max(all_values)
    fig, axes = plt.subplots(3, 2, figsize=(11, 15), constrained_layout=True)
    for row_index, label in enumerate(LABELS):
        for column, city in enumerate(CITIES):
            ax = axes[row_index, column]
            row = next(item for item in rows if item["city"] == city and item["label"] == label)
            events = evaluated(row["trace"])
            plot = ax.scatter(
                [item["east_km"] for item in events],
                [item["north_km"] for item in events],
                c=[item["weighted_mse_hz2"] ** 0.5 for item in events],
                s=10,
                cmap="viridis_r",
                vmin=shared_min,
                vmax=shared_max,
            )
            true_east, true_north = truth_offset(city, reference)
            selected, global_best = row["finest_selection"], row["global_incumbent"]
            ax.scatter(
                true_east,
                true_north,
                marker="+",
                s=150,
                color="black",
                label="reference (post-selection)",
            )
            ax.scatter(
                selected["east_km"],
                selected["north_km"],
                marker="*",
                s=150,
                color="red",
                edgecolor="black",
                label="finest selection",
            )
            if (global_best["east_km"], global_best["north_km"]) != (
                selected["east_km"],
                selected["north_km"],
            ):
                ax.scatter(
                    global_best["east_km"],
                    global_best["north_km"],
                    marker="D",
                    s=55,
                    color="cyan",
                    edgecolor="black",
                    label="all-level incumbent",
                )
            ax.add_patch(plt.Circle((0, 0), 500, fill=False, color="black", linewidth=0.7))
            ax.set(
                title=f"{city.title()} — {label}",
                xlabel="East (km)",
                ylabel="North (km)",
                aspect="equal",
            )
            ax.legend(fontsize=6)
            fig.colorbar(plot, ax=ax, label="RMSE (Hz), shared scale")
    fig.savefig(HERE / "visited-wide.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(3, 2, figsize=(11, 14), constrained_layout=True)
    for row_index, label in enumerate(LABELS):
        for column, city in enumerate(CITIES):
            ax = axes[row_index, column]
            row = next(item for item in rows if item["city"] == city and item["label"] == label)
            selected = row["finest_selection"]
            events = [
                item
                for item in evaluated(row["trace"])
                if math.hypot(
                    item["east_km"] - selected["east_km"], item["north_km"] - selected["north_km"]
                )
                <= 75
            ]
            values = [item["weighted_mse_hz2"] ** 0.5 for item in events]
            plot = ax.scatter(
                [item["east_km"] for item in events],
                [item["north_km"] for item in events],
                c=values,
                s=22,
                cmap="viridis_r",
                vmin=min(values),
                vmax=max(values),
            )
            true_east, true_north = truth_offset(city, reference)
            if math.hypot(true_east - selected["east_km"], true_north - selected["north_km"]) <= 75:
                ax.scatter(
                    true_east,
                    true_north,
                    marker="+",
                    s=150,
                    color="black",
                    label="reference",
                )
            else:
                ax.text(
                    0.02,
                    0.02,
                    f"true reference outside zoom; {row['postselection_distance_km']:.2f} km away",
                    transform=ax.transAxes,
                    fontsize=7,
                )
            ax.scatter(
                selected["east_km"],
                selected["north_km"],
                marker="*",
                s=160,
                color="red",
                edgecolor="black",
                label="finest selection",
            )
            ax.set(
                title=f"{city.title()} — {label}\nlocal ±75 km; panel-specific color range",
                xlabel="East (km)",
                ylabel="North (km)",
                aspect="equal",
            )
            ax.set_xlim(selected["east_km"] - 75, selected["east_km"] + 75)
            ax.set_ylim(selected["north_km"] - 75, selected["north_km"] + 75)
            ax.legend(fontsize=7)
            fig.colorbar(plot, ax=ax, label="RMSE (Hz), local scale")
    fig.savefig(HERE / "visited-local-zoom.png", dpi=180)
    plt.close(fig)

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
