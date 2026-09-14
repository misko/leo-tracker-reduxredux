#!/usr/bin/env python3
"""Plot acquisition evidence and real FPGA handoffs for comparable 30-MS/s dwells."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
CAMPAIGN = Path(
    "/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/"
    "five-300s-30ms-scan64-v1"
)
ROOT = CAMPAIGN.parent
PRIMARY = [f"recording-{index}" for index in range(1, 6)]
HISTORICAL = [
    ("prior live", ROOT / "live-scan64-30-v1", 1_690_312_500),
    ("prior confirmed RX", ROOT / "live-scan64-30-confirmed-rx-v1", 1_690_312_500),
    ("prior revisit CH3-a", ROOT / "scan64-revisit30-v1/visit-0", 1_690_312_500),
    ("prior revisit CH4", ROOT / "scan64-revisit30-v1/visit-1", 1_940_312_500),
    ("prior revisit CH3-b", ROOT / "scan64-revisit30-v1/visit-2", 1_690_312_500),
]


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def wilson(successes: int, trials: int) -> list[float]:
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return [center - half, center + half]


def summarize_run(run: dict) -> dict:
    return {
        key: value
        for key, value in run.items()
        if key != "attempts"
    } | {
        "maximum_single_pilot_power": max(
            item["max_single_pilot_power"] for item in run["attempts"]
        ),
        "handoff_events": [item for item in run["attempts"] if item["handoff"]],
    }


def review(
    name: str,
    path: Path,
    duration: float,
    frequency_hz: int,
    declared_attempt_count: int | None = None,
) -> dict:
    operator_path = path / "operator.json"
    if not operator_path.exists():
        operator_path = path.parent / "operator.json"
    operator = json.loads(operator_path.read_text())
    profile = operator.get("profile", operator.get("child_profile", ""))
    assert operator["rate"] == 30_000_000
    assert profile.endswith("selected-observer3-scan64")
    assert operator["candidate_budget"] == 64
    assert operator["ranking_fft"] == 4096
    rows = load_rows(path / "worker.jsonl")
    scans = [row for row in rows if row.get("kind") == "scan"]
    ranks = [row for row in rows if row.get("kind") == "candidate_order"]
    terminals = [row for row in rows if row.get("kind") == "worker_terminal"]
    assert len(ranks) == len(terminals)
    scan_by_attempt = {row["attempt"]: row for row in scans}
    assert [row["attempt"] for row in ranks] == [row["attempt"] for row in terminals]
    origin_ns = scans[0]["started_ns"]
    attempts = []
    for rank, terminal in zip(ranks, terminals, strict=True):
        scan = scan_by_attempt[rank["attempt"]]
        attempts.append(
            {
                "attempt": scan["attempt"],
                "elapsed_s": (scan["started_ns"] - origin_ns) / 1e9,
                "terminal_elapsed_s": (terminal["completed_ns"] - origin_ns) / 1e9,
                "max_single_pilot_power": max(rank["single_pilot_power"]),
                "handoff": terminal["status"] == 1,
            }
        )
    return {
        "name": name,
        "source": str(path),
        "duration_s": duration,
        "frequency_hz": frequency_hz,
        "attempt_count": (
            declared_attempt_count if declared_attempt_count is not None else len(attempts)
        ),
        "completed_attempts_plotted": len(attempts),
        "handoff_count": sum(item["handoff"] for item in attempts),
        "attempts": attempts,
    }


def main() -> None:
    campaign_summary = json.loads((HERE / "campaign-summary.json").read_text())
    campaign_runs = {
        run["name"]: run
        for run in campaign_summary["runs"]
        if run["name"] in PRIMARY
    }
    current = [
        review(
            name,
            CAMPAIGN / name,
            campaign_runs[name]["rf_seconds"],
            1_690_312_496,
            campaign_runs[name]["attempts"],
        )
        for name in PRIMARY
    ]
    historical = [review(name, path, 10.0663296, frequency) for name, path, frequency in HISTORICAL]

    current_successes = sum(run["handoff_count"] > 0 for run in current)
    historical_successes = sum(run["handoff_count"] > 0 for run in historical)
    current_handoffs = sum(run["handoff_count"] for run in current)
    historical_handoffs = sum(run["handoff_count"] for run in historical)
    current_attempts = sum(run["attempt_count"] for run in current)
    historical_attempts = sum(run["attempt_count"] for run in historical)
    current_seconds = sum(run["duration_s"] for run in current)
    historical_seconds = sum(run["duration_s"] for run in historical)

    summary = {
        "definition": (
            "A detection is status=1 in a worker_terminal row: an actual native FPGA handoff."
        ),
        "ranking_power_note": (
            "Maximum single-pilot ranking power is proposal evidence, not a detection threshold."
        ),
        "sample_rate_sps": 30_000_000,
        "exported_acquisition_rate_sps": 2_500_000,
        "current": {
            "dwell_count": len(current),
            "successful_dwells": current_successes,
            "dwell_success_fraction": current_successes / len(current),
            "dwell_success_wilson_95": wilson(current_successes, len(current)),
            "rf_seconds": current_seconds,
            "attempts": current_attempts,
            "handoffs": current_handoffs,
            "handoffs_per_1000_rf_seconds": current_handoffs / current_seconds * 1000,
            "handoffs_per_1000_attempts": current_handoffs / current_attempts * 1000,
        },
        "previous_comparable_scan64": {
            "selection": "All earlier 30-MS/s, 64-candidate, 4096-point-ranking scan64 dwells.",
            "dwell_count": len(historical),
            "successful_dwells": historical_successes,
            "dwell_success_fraction": historical_successes / len(historical),
            "dwell_success_wilson_95": wilson(historical_successes, len(historical)),
            "rf_seconds": historical_seconds,
            "attempts": historical_attempts,
            "handoffs": historical_handoffs,
            "handoffs_per_1000_rf_seconds": historical_handoffs / historical_seconds * 1000,
            "handoffs_per_1000_attempts": historical_handoffs / historical_attempts * 1000,
        },
        "current_runs": [summarize_run(run) for run in current],
        "previous_runs": [summarize_run(run) for run in historical],
    }
    (HERE / "detection-timeline-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    colors = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00"]
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), layout="constrained")
    for run, color in zip(current, colors, strict=True):
        x = [item["elapsed_s"] for item in run["attempts"]]
        y = [item["max_single_pilot_power"] for item in run["attempts"]]
        axes[0].plot(x, y, lw=1.0, alpha=0.9, color=color, label=run["name"])
        hits = [item for item in run["attempts"] if item["handoff"]]
        axes[0].scatter(
            [item["elapsed_s"] for item in hits],
            [item["max_single_pilot_power"] for item in hits],
            marker="*", s=180, color=color, edgecolor="black", linewidth=0.7, zorder=5,
        )
    axes[0].set(
        title="All five 30-MS/s recordings: acquisition evidence through time",
        xlabel="Elapsed recording time (s)",
        ylabel="Maximum single-pilot ranking power",
    )
    axes[0].text(
        0.99, 0.96, "star = actual FPGA handoff\nline = proposal evidence only",
        transform=axes[0].transAxes, ha="right", va="top", fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "0.8", "alpha": 0.9},
    )
    axes[0].grid(alpha=0.2)
    axes[0].legend(ncol=5, fontsize=8, loc="upper left")

    timeline = historical + current
    labels = [run["name"] for run in timeline]
    for row, run in enumerate(timeline):
        is_current = row >= len(historical)
        line_color = "#0072B2" if is_current else "0.55"
        axes[1].hlines(row, 0, run["duration_s"], color=line_color, lw=2.2, alpha=0.75)
        axes[1].scatter(
            [item["elapsed_s"] for item in run["attempts"]],
            [row] * len(run["attempts"]), s=7, marker="|", color=line_color, alpha=0.55,
        )
        hits = [item for item in run["attempts"] if item["handoff"]]
        axes[1].scatter(
            [item["terminal_elapsed_s"] for item in hits], [row] * len(hits),
            marker="*", s=130, color="#009E73", edgecolor="black", linewidth=0.6, zorder=5,
        )
    axes[1].axhline(len(historical) - 0.5, color="black", lw=0.8)
    axes[1].set(
        title="Actual handoffs versus all earlier comparable 30-MS/s scan64 dwells",
        xlabel="Elapsed dwell time (s)", ylabel="Dwell",
    )
    axes[1].set_yticks(range(len(labels)), labels)
    axes[1].invert_yaxis()
    axes[1].grid(axis="x", alpha=0.2)
    axes[1].text(
        0.99,
        0.96,
        "grey = previous 10.066-s dwells\nblue = current campaign\nstar = actual FPGA handoff",
        transform=axes[1].transAxes, ha="right", va="top", fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "0.8", "alpha": 0.9},
    )
    fig.savefig(HERE / "detection-timeline-comparison.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
