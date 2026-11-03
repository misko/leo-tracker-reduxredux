#!/usr/bin/env python3
"""Static figures for the complete, sealed 64-scan Student-t primary panel."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATASETS = ("DS9", "DS10", "DS11")
EXPECTED = {"DS9": 22, "DS10": 21, "DS11": 21}
CENTER = (38.5816, -121.4944)
REFERENCE = (37.849056280893684, -122.48575489722863)
EARTH_RADIUS_KM = 6371.0088


def validate_complete(evaluation: dict) -> list[dict]:
    """Reject partial or duplicate panels before making publication figures."""
    rows = evaluation.get("rows", [])
    if evaluation.get("schema") != "fixed-height-t4-primary-evaluation/v1":
        raise ValueError("unexpected evaluation schema")
    if evaluation.get("planned_units") != 64 or not evaluation.get("publication_ready"):
        raise ValueError("primary evaluation is not publication-ready")
    if len(rows) != 64 or len({row.get("unit_id") for row in rows}) != 64:
        raise ValueError("primary evaluation must contain 64 unique units")
    counts = Counter(row.get("dataset") for row in rows)
    if counts != Counter(EXPECTED):
        raise ValueError(f"dataset denominator mismatch: {dict(counts)}")
    if not all(row.get("attempted") for row in rows):
        raise ValueError("every planned unit must have an attempt record")
    for row in rows:
        accepted = bool(row.get("accepted"))
        converged = bool(row.get("native_numerically_converged",
                                 row.get("numerically_converged")))
        if not accepted and not converged:
            continue
        reported_error = (row.get("error_m") if accepted
                          else row.get("failed_point_error_m_diagnostic"))
        point = (row.get("east_km"), row.get("north_km"), reported_error)
        if not row.get("sealed") or any(value is None or not np.isfinite(value) for value in point):
            raise ValueError("every accepted or converged row must be sealed with a finite point")
        if accepted and row.get("error_m") is None:
            raise ValueError("accepted row lacks an accepted error")
    return rows


def failure_aware_ecdf(rows: list[dict], key: str) -> tuple[np.ndarray, np.ndarray]:
    """Return finite errors with ordinates divided by all planned rows."""
    values = np.sort([float(row[key]) for row in rows if row.get(key) is not None])
    return values, np.arange(1, values.size + 1, dtype=float) / len(rows)


def _reference_en() -> tuple[float, float]:
    lat1, lon1 = map(math.radians, CENTER)
    lat2, lon2 = map(math.radians, REFERENCE)
    dlon = lon2 - lon1
    central = math.acos(
        np.clip(
            math.sin(lat1) * math.sin(lat2)
            + math.cos(lat1) * math.cos(lat2) * math.cos(dlon),
            -1,
            1,
        )
    )
    bearing = math.atan2(
        math.sin(dlon) * math.cos(lat2),
        math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon),
    )
    distance = EARTH_RADIUS_KM * central
    return distance * math.sin(bearing), distance * math.cos(bearing)


def generate(evaluation: dict, output: Path) -> list[Path]:
    rows = validate_complete(evaluation)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    fig, axis = plt.subplots(figsize=(7.5, 5), constrained_layout=True)
    for key, label, color in (
        ("error_m", "Student-t joint", "tab:blue"),
        ("old_greedy_error_m", "Previous greedy", "tab:orange"),
    ):
        x, y = failure_aware_ecdf(rows, key)
        if x.size:
            axis.step(x, y, where="post", marker="o", markersize=3, color=color,
                      label=f"{label}: {x.size}/64 finite accepted errors")
        else:
            axis.plot([], [], color=color, label=f"{label}: 0/64 finite accepted errors")
    axis.axvline(1000, color="tab:red", linestyle="--", linewidth=1, label="1 km")
    axis.axvline(10000, color="0.35", linestyle=":", linewidth=1, label="10 km")
    axis.set(xscale="log", ylim=(0, 1.02), xlabel="roof-reference error (m)",
             ylabel="fraction of all 64 planned scans",
             title="Failure-aware empirical CDF")
    axis.legend(fontsize="small")
    path = output / "primary-error-ecdf-all64.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    paired = [row for row in rows if row.get("accepted")
              and row.get("error_m") is not None
              and row.get("old_greedy_error_m") is not None]
    fig, axis = plt.subplots(figsize=(6, 6), constrained_layout=True)
    if paired:
        old = np.array([row["old_greedy_error_m"] for row in paired], dtype=float)
        new = np.array([row["error_m"] for row in paired], dtype=float)
        for dataset, marker in zip(DATASETS, ("o", "s", "^"), strict=True):
            use = np.array([row["dataset"] == dataset for row in paired])
            axis.scatter(old[use], new[use], marker=marker, alpha=0.75,
                         label=f"{dataset} ({use.sum()})")
        bounds = [max(1, min(old.min(), new.min()) * 0.7), max(old.max(), new.max()) * 1.4]
        axis.plot(bounds, bounds, color="0.25", linestyle="--", label="equal error")
        axis.set(xlim=bounds, ylim=bounds)
    else:
        axis.text(0.5, 0.5, "No paired accepted scans", transform=axis.transAxes, ha="center")
    axis.set(xscale="log", yscale="log", xlabel="previous greedy error (m)",
             ylabel="Student-t joint error (m)", title="Matched accepted scans only")
    axis.legend(fontsize="small")
    path = output / "primary-paired-errors.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.3), sharey=True, constrained_layout=True)
    categories = ("processing\ncomplete", "numerically\nconverged", "not\nconverged", ">10 km")
    for axis, dataset in zip(axes, DATASETS, strict=True):
        subset = [row for row in rows if row["dataset"] == dataset]
        values = (
            sum(bool(row.get("processing_complete")) for row in subset),
            sum(bool(row.get("numerically_converged")) for row in subset),
            sum(not bool(row.get("numerically_converged")) for row in subset),
            sum(row.get("accepted") and row.get("error_m") is not None
                and row["error_m"] > 10000 for row in subset),
        )
        bars = axis.bar(
            categories,
            values,
            color=("tab:blue", "tab:green", "tab:red", "tab:purple"),
        )
        axis.bar_label(bars)
        axis.set(title=f"{dataset} (n={len(subset)})", ylim=(0, max(EXPECTED.values()) + 2))
        axis.tick_params(axis="x", rotation=25)
    axes[0].set_ylabel("scans")
    fig.suptitle("Numerical convergence and catastrophic accepted errors")
    path = output / "primary-status-by-dataset.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    fig, axis = plt.subplots(figsize=(6.5, 6.5), constrained_layout=True)
    for dataset, marker in zip(DATASETS, ("o", "s", "^"), strict=True):
        subset = [row for row in rows if row["dataset"] == dataset
                  and row.get("accepted") and row.get("error_m") is not None]
        axis.scatter([row["east_km"] for row in subset], [row["north_km"] for row in subset],
                     marker=marker, alpha=0.75, label=f"{dataset} accepted ({len(subset)})")
    axis.add_patch(plt.Circle((0, 0), 250, fill=False, color="0.3", linewidth=1.4,
                              label="Sacramento 250 km prior disk"))
    reference_east, reference_north = _reference_en()
    axis.scatter(0, 0, marker="+", s=100, color="black", label="Sacramento center")
    axis.scatter(reference_east, reference_north, marker="*", s=130, color="tab:red",
                 label="roof reference (evaluation only)")
    axis.set(xlabel="east from Sacramento (km)", ylabel="north from Sacramento (km)",
             title="Accepted final points; failures omitted", aspect="equal")
    axis.legend(fontsize="small", loc="upper left", bbox_to_anchor=(1.02, 1))
    path = output / "primary-spatial-context.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(path)

    fig, axis = plt.subplots(figsize=(6.5, 6), constrained_layout=True)
    accepted = [row for row in rows if row.get("accepted") and row.get("error_m") is not None]
    offsets = np.array([
        ((row["east_km"] - reference_east) * 1000,
         (row["north_km"] - reference_north) * 1000)
        for row in accepted
    ]) if accepted else np.empty((0, 2))
    inside = np.linalg.norm(offsets, axis=1) <= 5000
    for dataset, marker in zip(DATASETS, ("o", "s", "^"), strict=True):
        use = np.array([row["dataset"] == dataset for row in accepted]) & inside
        axis.scatter(offsets[use, 0], offsets[use, 1], marker=marker, alpha=0.8,
                     label=f"{dataset} within 5 km ({use.sum()})")
    axis.scatter(0, 0, marker="*", s=150, color="tab:red", label="roof reference")
    axis.set(xlim=(-5000, 5000), ylim=(-5000, 5000), aspect="equal",
             xlabel="east of roof reference (m)", ylabel="north of roof reference (m)",
             title=f"Roof-centered 5 km view; {(~inside).sum()} accepted points outside")
    axis.legend(fontsize="small", loc="upper left", bbox_to_anchor=(1.02, 1))
    path = output / "primary-spatial-roof-zoom.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.evaluation.read_text())
    for path in generate(document, args.output):
        print(path)


if __name__ == "__main__":
    main()
