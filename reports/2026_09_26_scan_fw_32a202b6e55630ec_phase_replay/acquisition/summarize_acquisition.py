#!/usr/bin/env python3
"""Summarize the frozen smoke ablation and render acquisition coordinates."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def summarize(scratch: Path, report: Path) -> None:
    smoke = json.loads((report.parent / "selection.json").read_text())["smoke8_visit_indices"]
    corrected: dict[tuple[int, int], float] = {}
    points = []
    with (report / "candidate-inventory.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            visit = int(row["visit_index"])
            receiver = int(row["receiver_id"])
            margin = float(row["fractional_margin"])
            corrected[visit, receiver] = max(
                corrected.get((visit, receiver), float("-inf")), margin
            )
            points.append(
                (
                    float(row["tracking_absolute_baseband_cfo_hz"]),
                    int(row["integer_epoch_sample"]),
                    margin,
                )
            )
    rows = []
    confusion: Counter[str] = Counter()
    for visit in smoke:
        legacy = json.loads((scratch / f"visit-{visit:06d}.legacy-sparse.json").read_text())
        for probe in legacy["analysis"]["probes"]:
            receiver = int(probe["receiver_id"])
            legacy_margin = max(
                (
                    float(item["fractional_margin"])
                    for item in probe["candidates"]
                    if item["fractional_margin"] is not None
                ),
                default=float("-inf"),
            )
            corrected_margin = corrected[visit, receiver]
            legacy_pass = legacy_margin >= 0.025
            corrected_pass = corrected_margin >= 0.025
            cell = (
                "both"
                if legacy_pass and corrected_pass
                else "legacy_only"
                if legacy_pass
                else "corrected_only"
                if corrected_pass
                else "neither"
            )
            confusion[cell] += 1
            for data_variant in ("raw", "rf_valid"):
                rows.append(
                    {
                        "visit_index": visit,
                        "receiver_id": receiver,
                        "data_variant": data_variant,
                        "legacy_best_margin": legacy_margin,
                        "corrected_best_margin": corrected_margin,
                        "legacy_passed": legacy_pass,
                        "corrected_passed": corrected_pass,
                        "confusion_cell": cell,
                        "raw_valid_identical": True,
                    }
                )
    fields = tuple(rows[0])
    with (report / "legacy-corrected-confusion.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (report / "legacy-corrected-confusion.json").write_text(
        json.dumps(
            {
                "cohort": "selection.json smoke8 (16 receiver probes)",
                "counts": dict(confusion),
                "raw_valid_axis": "identical: full capture audit found zero invalid rows",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    frequency, epoch, margin = zip(*points, strict=True)
    figure, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    scatter = axes[0].scatter(
        frequency, epoch, c=margin, s=3, cmap="coolwarm", vmin=-0.05, vmax=0.25
    )
    axes[0].set_xlabel("tracking absolute baseband CFO (Hz)")
    axes[0].set_ylabel("integer epoch sample in 20 ms probe")
    axes[0].set_title("Corrected sparse census: retained basins")
    figure.colorbar(scatter, ax=axes[0], label="fractional exact-control margin")
    axes[1].hist(margin, bins=100, range=(-0.1, 0.8), color="#315b7d")
    axes[1].axvline(0.025, color="crimson", linestyle="--", label="comparison gate 0.025")
    axes[1].set_xlabel("fractional exact-control margin")
    axes[1].set_ylabel("candidate count")
    axes[1].set_title("Margin distribution")
    axes[1].legend()
    figure.savefig(report / "frequency-epoch-margin.png", dpi=150)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    summarize(args.scratch, args.report)


if __name__ == "__main__":
    main()
