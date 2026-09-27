#!/usr/bin/env python3
"""Render sealed DS5 portable post-seal evaluation tables and figures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


METHOD_LABELS = {
    "baseline": "Baseline",
    "shared_global_tau": "Shared time",
    "regularized_per_scan_tau": "Per-scan time",
    "independent_per_track_tau": "Per-track time",
    "causal_per_norad_orbit_rate": "Per-NORAD rate",
    "global_tau_per_norad_orbit_rate": "Time + rate",
    "soft_joint_association": "Soft identity",
    "soft_association_global_tau": "Soft identity + time",
}
RATES = (2_500_000, 5_000_000, 7_500_000, 10_000_000)
STRATA = ("low", "middle", "high")


def seal(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


def summary_index(document: dict[str, Any], name: str) -> dict[tuple[str, ...], dict[str, Any]]:
    return {tuple(row["key"]): row for row in document["summaries"][name]}


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Method | Single median km | Group8 median km | Full km | Rate-full median km | Complete |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        def value(name: str) -> str:
            number = row.get(name)
            return "pending" if number is None else f"{number:.3f}"
        lines.append(
            f"| {row['method_label']} | {value('single_median_error_km')} | "
            f"{value('group8_median_error_km')} | {value('full_error_km')} | "
            f"{value('rate_full_median_error_km')} | {row['complete_count']}/{row['expected_count']} |"
        )
    return "\n".join(lines)


def comparison_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    index = summary_index(document, "scope_method")
    answer = []
    for method, label in METHOD_LABELS.items():
        scope = {name: index.get((name, method), {}) for name in ("single", "group8", "full", "rate_full")}
        full = scope["full"]
        answer.append({
            "method": method,
            "method_label": label,
            "single_median_error_km": scope["single"].get("median_error_km"),
            "group8_median_error_km": scope["group8"].get("median_error_km"),
            "full_error_km": full.get("median_error_km"),
            "rate_full_median_error_km": scope["rate_full"].get("median_error_km"),
            "complete_count": sum(int(scope[name].get("complete_count", 0)) for name in scope),
            "expected_count": sum(int(scope[name].get("expected_count", 0)) for name in scope),
        })
    return answer


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    seal(path)


def plot_scope_comparison(path: Path, rows: list[dict[str, Any]]) -> None:
    x = np.arange(len(rows))
    width = 0.2
    fig, ax = plt.subplots(figsize=(14, 7), constrained_layout=True)
    for offset, (field, label) in enumerate((
        ("single_median_error_km", "Single median"),
        ("group8_median_error_km", "Group8 median"),
        ("full_error_km", "Full 42"),
        ("rate_full_median_error_km", "Rate-full median"),
    )):
        values = [np.nan if row[field] is None else row[field] for row in rows]
        ax.bar(x + (offset - 1.5) * width, values, width, label=label)
    ax.set_xticks(x, [row["method_label"] for row in rows], rotation=28, ha="right")
    ax.set_ylabel("Horizontal position error (km)")
    ax.set_title("DS5 portable positioning methods · post-seal reference evaluation")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    seal(path)


def plot_rate_active(path: Path, document: dict[str, Any]) -> None:
    index = summary_index(document, "single_rate_active_method")
    fig, axes = plt.subplots(2, 4, figsize=(18, 9), constrained_layout=True, sharex=True, sharey=True)
    finite: list[float] = []
    matrices: dict[str, np.ndarray] = {}
    for method in METHOD_LABELS:
        matrix = np.full((len(STRATA), len(RATES)), np.nan)
        for y, stratum in enumerate(STRATA):
            for x, rate in enumerate(RATES):
                value = index.get((str(rate), stratum, method), {}).get("median_error_km")
                if value is not None:
                    matrix[y, x] = value
                    finite.append(float(value))
        matrices[method] = matrix
    vmax = np.nanpercentile(finite, 90) if finite else 1.0
    for ax, (method, label) in zip(axes.flat, METHOD_LABELS.items(), strict=True):
        image = ax.imshow(matrices[method], aspect="auto", vmin=0, vmax=vmax, cmap="viridis_r")
        ax.set_title(label)
        ax.set_xticks(range(len(RATES)), [f"{rate / 1e6:g}" for rate in RATES])
        ax.set_yticks(range(len(STRATA)), STRATA)
        for y in range(len(STRATA)):
            for x in range(len(RATES)):
                value = matrices[method][y, x]
                ax.text(x, y, "pending" if np.isnan(value) else f"{value:.1f}", ha="center", va="center", fontsize=8)
    fig.supxlabel("Sample rate (MS/s)")
    fig.supylabel("Truth-blind active-time stratum")
    fig.suptitle("DS5 single-scan median error by sample rate and valid active time")
    fig.colorbar(image, ax=axes, label="Median horizontal error (km)", shrink=0.8)
    fig.savefig(path, dpi=180)
    plt.close(fig)
    seal(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    document = json.loads(args.evaluation.read_text())
    if document["pending_result_count"] and not args.allow_incomplete:
        raise ValueError(f"portable evaluation still has {document['pending_result_count']} pending rows")
    rows = comparison_rows(document)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "portable-comparison.csv", rows)
    singles = [row for row in document["rows"] if row["scope"] == "single"]
    write_csv(args.output_dir / "portable-single-results.csv", singles)
    plot_scope_comparison(args.output_dir / "portable-scope-comparison.png", rows)
    plot_rate_active(args.output_dir / "portable-rate-active-heatmap.png", document)
    report = (
        "# DS5 portable raw-track methods\n\n"
        "All inference was sealed without a reference coordinate. Horizontal error was added only by the post-seal evaluator. "
        f"The matrix contains {document['complete_result_count']}/{document['expected_result_count']} completed fits.\n\n"
        + markdown_table(rows)
        + "\n\nThe rate × active-time heatmap uses the sealed truth-blind active-time terciles and preserves each scan's recorded sample rate. "
        "Chronological group8 membership was not reordered by rate.\n"
    )
    report_path = args.output_dir / "PORTABLE_REPORT.md"
    report_path.write_text(report)
    seal(report_path)


if __name__ == "__main__":
    main()
