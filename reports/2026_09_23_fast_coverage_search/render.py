#!/usr/bin/env python3
"""Verify and render the frozen fast-coverage benchmark summary."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
CITIES = ("sacramento", "reno", "denver")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def main():
    benchmark_path = HERE / "inputs" / "benchmark-summary.json"
    benchmark = read(benchmark_path)
    assert benchmark["schema"] == "fast-coverage-search-benchmark/v1"
    assert benchmark["complete"] is True
    assert benchmark["session_id"] == "scan-fw-cf510316ae7f05d5"
    assert benchmark["unique_observation_count"] == 372
    assert benchmark["primary_threshold_hz_strict_less_than"] == 200
    assert benchmark["partition_mode"] == "fixed-per-track-position-independent"
    assert {row["city"] for row in benchmark["runs"]} == set(CITIES)

    reference_path = HERE / "inputs" / "evaluation-reference.json"
    reference = read(reference_path)
    rows = []
    for run in benchmark["runs"]:
        assert run["evaluated_points"] > 0
        assert run["timing_s"]["prepare"] >= 0
        assert run["timing_s"]["search"] >= 0
        assert run["timing_s"]["finalist_recompute"] >= 0
        if run["top_k_recall"] is not None:
            assert 0 <= run["top_k_recall"] <= 1
        if run["objective_gap"] is not None:
            assert run["objective_gap"] >= 0
        assert run["finalist"]["unique_observation_count"] <= 372
        row = dict(run)
        row["postselection_evaluation_distance_km"] = distance_km(
            run["finalist"]["latitude_deg"],
            run["finalist"]["longitude_deg"],
            reference["latitude_deg"],
            reference["longitude_deg"],
        )
        rows.append(row)

    output = {
        "schema": "fast-coverage-search-report/v1",
        "benchmark_digest": digest(benchmark_path),
        "evaluation_reference_digest": digest(reference_path),
        "evaluation_reference_used_after_selection_only": True,
        "runs": rows,
    }
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")

    fig, axes = plt.subplots(2, 3, figsize=(14, 7), constrained_layout=True)
    for column, city in enumerate(CITIES):
        city_rows = [row for row in rows if row["city"] == city]
        labels = [row["label"] for row in city_rows]
        axes[0, column].bar(labels, [row["timing_s"]["search"] for row in city_rows])
        axes[1, column].bar(
            labels,
            [row["evaluated_points"] for row in city_rows],
            color="#e45756",
        )
        axes[0, column].set_title(city.title())
        axes[0, column].set_ylabel("Search seconds")
        axes[1, column].set_ylabel("Requested centers")
        for ax in axes[:, column]:
            ax.tick_params(axis="x", rotation=30, labelsize=7)
    fig.savefig(HERE / "runtime-and-work.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for ax, city in zip(axes, CITIES, strict=True):
        row = next(item for item in rows if item["city"] == city and item["mode"] == "adaptive")
        progress = row["resolution_progress"]
        ax.plot(
            [item["spacing_km"] for item in progress],
            [item["cumulative_points"] for item in progress],
            marker="o",
        )
        ax.set(title=city.title(), xlabel="Grid spacing (km)", ylabel="Cumulative centers")
        ax.invert_xaxis()
    fig.savefig(HERE / "resolution-work.png", dpi=180)
    plt.close(fig)

    progression = read(HERE / "inputs" / "fine32-level-progression-v1.json")
    assert progression["schema"] == "fast-coverage-level-progression/v1"
    assert progression["complete"] is True and progression["truth_accessed"] is False
    fig, axes = plt.subplots(2, 3, figsize=(14, 7), constrained_layout=True)
    for column, city in enumerate(CITIES):
        progress = progression["cities"][city]["levels"]
        spacing = [item["spacing_km"] for item in progress]
        for label, field, style in (
            ("current level", "level_inside_leader", "o-"),
            ("evaluated union", "union_incumbent", "s--"),
        ):
            coverage = [item[field]["coverage"][0] for item in progress]
            axes[0, column].plot(
                spacing,
                [item["unique_observation_count"] for item in coverage],
                style,
                label=label,
            )
            axes[1, column].plot(
                spacing,
                [item["clipped_best_rms_sum_hz"] for item in coverage],
                style,
                label=label,
            )
        axes[0, column].set_title(city.title())
        axes[0, column].set_ylabel("Covered observations")
        axes[1, column].set_ylabel("Clipped RMS sum (Hz)")
        axes[1, column].set_xlabel("Grid spacing (km)")
        for ax in axes[:, column]:
            ax.invert_xaxis()
            ax.grid(alpha=0.2)
        axes[0, column].legend(fontsize=7)
    fig.savefig(HERE / "coverage-vs-resolution.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    x = range(len(CITIES))
    width = 0.36
    for offset, mode, label in (
        (-width / 2, "adaptive", "coarse-seeded beam 32"),
        (width / 2, "adaptive-seeded", "exact-50 top-15 seeded"),
    ):
        selected = [
            next(row for row in rows if row["city"] == city and row["mode"] == mode)
            for city in CITIES
        ]
        axes[0].bar(
            [value + offset for value in x],
            [row["finalist"]["unique_observation_count"] for row in selected],
            width,
            label=label,
        )
        axes[1].bar(
            [value + offset for value in x],
            [row["postselection_evaluation_distance_km"] for row in selected],
            width,
            label=label,
        )
    for ax in axes:
        ax.set_xticks(list(x), [city.title() for city in CITIES])
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Covered observations")
    axes[0].set_ylim(250, 380)
    axes[1].set_ylabel("Post-selection distance (km, log scale)")
    axes[1].set_yscale("log")
    axes[0].legend(fontsize=8)
    fig.savefig(HERE / "pipeline-outcomes.png", dpi=180)
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
