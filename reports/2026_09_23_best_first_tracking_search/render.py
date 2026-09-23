#!/usr/bin/env python3
"""Render the qualified best-first benchmark."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


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
        circle = plt.Circle((0, 0), 500, fill=False, color="black", linewidth=0.8)
        ax.add_patch(circle)
        ax.set(title=city.title(), xlabel="East (km)", ylabel="North (km)", aspect="equal")
        ax.legend(fontsize=8)
        fig.colorbar(plot, ax=ax, label="Capped weighted RMSE (Hz)")
    fig.savefig(HERE / "visited-points.png", dpi=180)
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
