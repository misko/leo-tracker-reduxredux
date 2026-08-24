#!/usr/bin/env python3
"""Render the compact continuity-buffer implementation summary figure."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_24_continuity_buffer_implementation"
    / "continuity-buffer-evidence.json"
)
DEFAULT_OUTPUT = DEFAULT_EVIDENCE.with_name("continuity-buffer-verification.png")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError("expected continuity-buffer evidence schema version 2")
    return payload


def render(evidence_path: Path, output_path: Path) -> None:
    evidence = _load(evidence_path)
    controlled = evidence["controlled_131072_sample_refill"]
    dwell = evidence["post_deploy_paired_60_second_dwell"]
    scanner = evidence["post_deploy_scanner_four_sweep"]
    historical_dwell = evidence["paired_60_second_dwell"]
    historical_scanner = evidence["scanner_eight_target"]

    buffers = [row["kernel_buffers"] for row in controlled]
    gap_fraction = [100.0 * row["gap_boundaries"] / row["tested_boundaries"] for row in controlled]

    matplotlib.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "figure.facecolor": "#f7fafc",
            "axes.facecolor": "#ffffff",
        }
    )
    figure, axes = plt.subplots(1, 3, figsize=(16.8, 5.0), constrained_layout=True)
    figure.suptitle(
        "Counter-authoritative Pluto capture: deployed red/green, runtime, and coverage",
        fontsize=15,
        fontweight="bold",
        color="#17324d",
    )

    ax = axes[0]
    colors = ["#d95f59" if value else "#2a9d8f" for value in gap_fraction]
    bars = ax.bar([str(value) for value in buffers], gap_fraction, color=colors, width=0.68)
    ax.set_title("A · FPGA-counter gaps at each buffer depth", loc="left", fontweight="bold")
    ax.set_xlabel("kernel RX buffers (K)")
    ax.set_ylabel("boundaries with a counter gap (%)")
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.22)
    for bar, row, fraction in zip(bars, controlled, gap_fraction, strict=True):
        label = f"{row['gap_boundaries']}/{row['tested_boundaries']}"
        y = fraction - 16.0 if fraction else 3.0
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y,
            label,
            ha="center",
            fontweight="bold",
            color="white" if fraction else "black",
        )
    ax.text(
        0.02,
        0.96,
        "131,072 samples/refill · 2.5 MS/s\nK=1 loses whole blocks; K≥2 is green in this test",
        transform=ax.transAxes,
        va="top",
        color="#334e68",
        bbox={"facecolor": "#edf6f9", "edgecolor": "#b8d8df", "pad": 5},
    )

    ax = axes[1]
    labels = ["60 s paired dwell", "8-target scanner"]
    legacy = [
        historical_dwell["legacy_recent_create_to_finalize_wall_seconds"],
        sum(historical_scanner["recent_v1_wall_seconds_range"]) / 2,
    ]
    v2 = [
        dwell["create_to_finalize_wall_seconds"],
        statistics.median(scanner["capture_elapsed_seconds"]),
    ]
    x = [0, 1]
    width = 0.34
    old_bars = ax.bar(
        [value - width / 2 for value in x],
        legacy,
        width,
        color="#9aa6b2",
        label="recent V1 reference",
    )
    new_bars = ax.bar(
        [value + width / 2 for value in x],
        v2,
        width,
        color="#2878b5",
        label="continuity V2",
    )
    ax.set_yscale("log")
    ax.set_xticks(x, labels)
    ax.set_ylabel("capture wall time (s, log scale)")
    ax.set_title("B · Measured capture runtime", loc="left", fontweight="bold")
    ax.grid(axis="y", which="both", alpha=0.22)
    ax.legend(frameon=False, loc="upper right")
    for bars_group in (old_bars, new_bars):
        for bar in bars_group:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.07,
                f"{bar.get_height():.2f}s",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax = axes[2]
    verified = [
        dwell["verified_counter_boundaries"][0],
        dwell["verified_counter_boundaries"][1],
        scanner["attested_target_frames"],
    ]
    expected = [
        dwell["counter_boundaries_per_radio"],
        dwell["counter_boundaries_per_radio"],
        scanner["sweep_count"] * scanner["targets_per_sweep"],
    ]
    coverage = [100.0 * good / total for good, total in zip(verified, expected, strict=True)]
    bars = ax.bar(
        ["dwell .20", "dwell .21", "scanner"],
        coverage,
        color="#2a9d8f",
        width=0.68,
    )
    ax.set_title("C · Exact deployed continuity evidence", loc="left", fontweight="bold")
    ax.set_ylabel("counter/frame checks passing (%)")
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.22)
    for bar, good, total in zip(bars, verified, expected, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            92,
            f"{good}/{total}",
            ha="center",
            fontweight="bold",
            color="white",
        )
    ax.text(
        0.02,
        0.08,
        "0 gaps · 0 missing · 0 overflow\nK=8 read back on every episode",
        transform=ax.transAxes,
        va="bottom",
        color="#334e68",
        bbox={"facecolor": "#edf6f9", "edgecolor": "#b8d8df", "pad": 5},
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output_path,
        dpi=180,
        metadata={"Software": "leo-tracker-reduxredux"},
    )
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    render(args.evidence, args.output)


if __name__ == "__main__":
    main()
