#!/usr/bin/env python3
"""Compare the frozen 90-second primary and bounded 180-second continuation."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from plot_primary import DATASETS, EXPECTED, failure_aware_ecdf, validate_complete


def validate_continuation(document: dict) -> list[dict]:
    if document.get("schema") != "fixed-height-t4-continuation-evaluation/v1":
        raise ValueError("unexpected continuation evaluation schema")
    if document.get("planned_units") != 64 or not document.get("publication_ready"):
        raise ValueError("continuation evaluation is not publication-ready")
    rows = document.get("rows", [])
    if len(rows) != 64 or len({row.get("unit_id") for row in rows}) != 64:
        raise ValueError("continuation evaluation must contain 64 unique units")
    if Counter(row.get("dataset") for row in rows) != Counter(EXPECTED):
        raise ValueError("continuation dataset denominators do not match 22/21/21")
    primary_document = {
        "schema": "fixed-height-t4-primary-evaluation/v1",
        "planned_units": 64,
        "publication_ready": True,
        "rows": [row["primary"] for row in rows],
    }
    validate_complete(primary_document)
    for row in rows:
        primary_accepted = bool(row["primary"].get("accepted"))
        primary_converged = bool(row["primary"].get(
            "native_numerically_converged",
            row["primary"].get("numerically_converged"),
        ))
        if not primary_accepted and not primary_converged and not row.get("continuation_attempted"):
            raise ValueError("every unresolved primary requires a continuation attempt")
        if not row.get("effective_accepted"):
            continue
        point = (row.get("effective_east_km"), row.get("effective_north_km"),
                 row.get("effective_error_m"))
        if any(value is None or not np.isfinite(value) for value in point):
            raise ValueError("accepted continuation outcome lacks a finite point")
        if not primary_accepted and not row.get("continuation", {}).get("sealed"):
            raise ValueError("accepted resumed outcome must be sealed")
    return rows


def generate(document: dict, output: Path) -> list[Path]:
    rows = validate_continuation(document)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    primary_rows = [row["primary"] for row in rows]
    fig, axis = plt.subplots(figsize=(7.5, 5), constrained_layout=True)
    for values, key, label, color in (
        (primary_rows, "error_m", "Original 90-second method", "tab:orange"),
        (rows, "effective_error_m", "Two-stage 180-second method", "tab:blue"),
    ):
        x, y = failure_aware_ecdf(values, key)
        if x.size:
            axis.step(x, y, where="post", marker="o", markersize=3, color=color,
                      label=f"{label}: {x.size}/64 accepted")
        else:
            axis.plot([], [], color=color, label=f"{label}: 0/64 accepted")
    axis.axvline(1000, color="tab:red", linestyle="--", linewidth=1, label="1 km")
    axis.axvline(10000, color="0.35", linestyle=":", linewidth=1, label="10 km")
    axis.set(xscale="log", ylim=(0, 1.02), xlabel="roof-reference error (m)",
             ylabel="fraction of all 64 planned scans",
             title="Failure-aware continuation comparison")
    axis.legend(fontsize="small")
    path = output / "continuation-error-ecdf-all64.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path)

    dataset_order = {name: index for index, name in enumerate(DATASETS)}
    ordered = sorted(rows, key=lambda row: (dataset_order[row["dataset"]], row["unit_id"]))
    x = np.arange(64)
    primary_error = np.array([
        np.nan if row["primary"].get("error_m") is None else row["primary"]["error_m"]
        for row in ordered
    ])
    effective_error = np.array([
        np.nan if row.get("effective_error_m") is None else row["effective_error_m"]
        for row in ordered
    ])
    finite = np.r_[primary_error[np.isfinite(primary_error)],
                   effective_error[np.isfinite(effective_error)]]
    failure_level = max(20000.0, float(finite.max()) * 1.7 if finite.size else 20000.0)
    fig, (errors, status) = plt.subplots(
        2, 1, figsize=(14, 6), constrained_layout=True, sharex=True,
        gridspec_kw={"height_ratios": (4, 1)},
    )
    errors.scatter(x[np.isfinite(primary_error)], primary_error[np.isfinite(primary_error)],
                   marker="o", s=22, color="tab:orange", label="90 s accepted")
    errors.scatter(x[np.isfinite(effective_error)], effective_error[np.isfinite(effective_error)],
                   marker="x", s=30, color="tab:blue", label="180 s accepted")
    errors.scatter(x[~np.isfinite(primary_error)],
                   np.full((~np.isfinite(primary_error)).sum(), failure_level),
                   marker="v", s=22, color="tab:orange", label="90 s failure")
    errors.scatter(x[~np.isfinite(effective_error)],
                   np.full((~np.isfinite(effective_error)).sum(), failure_level * 1.08),
                   marker="^", s=22, color="tab:blue", label="180 s failure")
    errors.axhline(1000, color="tab:red", linestyle="--", linewidth=1)
    errors.set(yscale="log", ylabel="error (m)",
               title="Per-scan accepted error and explicit failure markers")
    errors.legend(fontsize="small", ncol=2)
    primary_ok = np.isfinite(primary_error).astype(float)
    effective_ok = np.isfinite(effective_error).astype(float)
    status.imshow(np.vstack((primary_ok, effective_ok)), aspect="auto", interpolation="nearest",
                  cmap=matplotlib.colors.ListedColormap(["#c44e52", "#55a868"]), vmin=0, vmax=1)
    status.set(yticks=(0, 1), yticklabels=("90 s", "180 s"), xlabel="scan, grouped by dataset")
    boundaries = np.cumsum([EXPECTED[name] for name in DATASETS[:-1]]) - 0.5
    for axis in (errors, status):
        for boundary in boundaries:
            axis.axvline(boundary, color="0.4", linewidth=0.8)
    status.set_xticks((10.5, 31.5, 52.5), ("DS9", "DS10", "DS11"))
    path = output / "continuation-per-scan-errors-status.png"
    fig.savefig(path, dpi=180)
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
