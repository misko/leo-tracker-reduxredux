#!/usr/bin/env python3
"""Plot qualified tracking time and historical 2.5-MS/s duty comparisons."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main() -> None:
    detection = json.loads((HERE / "detection-timeline-summary.json").read_text())
    campaign = json.loads((HERE / "campaign-summary.json").read_text())
    run_by_name = {run["name"]: run for run in campaign["runs"]}

    # A native episode begins at its acquisition handoff. Its result count at
    # the fixed 750-Hz schedule determines the retained qualified interval.
    timeline = []
    for run in detection["current_runs"]:
        episodes = run_by_name[run["name"]].get("native_episodes", [])
        handoffs = run["handoff_events"]
        active_episodes = [episode for episode in episodes if episode["results"]]
        assert len(handoffs) == len(active_episodes)
        intervals = []
        for handoff, episode in zip(handoffs, active_episodes, strict=True):
            start = handoff["terminal_elapsed_s"]
            duration = episode["results"] / 750.0
            intervals.append(
                {
                    "start_s": start,
                    "end_s": start + duration,
                    "duration_s": duration,
                    "results": episode["results"],
                    "supported": episode["supported"],
                }
            )
        timeline.append(
            {
                "name": run["name"],
                "duration_s": run["duration_s"],
                "handoff_times_s": [event["terminal_elapsed_s"] for event in handoffs],
                "qualified_tracking_intervals": intervals,
            }
        )

    historical = [
        {
            "name": "Sep 10 live adaptive",
            "positive": 1991,
            "visits": 2357,
            "capture_duty_percent": 94.2621,
            "source": "reports/2026_09_10_scanner_live.md",
        },
        {
            "name": "Sep 10 LNB verification",
            "positive": 1452,
            "visits": 2364,
            "capture_duty_percent": 94.5317,
            "source": "reports/2026_09_10_scanner_lnb_live_checkpoint.md",
        },
        {
            "name": "Sep 10 production rollout",
            "positive": 1475,
            "visits": 2364,
            "capture_duty_percent": 94.5483,
            "source": "reports/2026_09_10_scanner_production_rollout.md",
        },
    ]
    for item in historical:
        item["positive_visit_percent"] = 100.0 * item["positive"] / item["visits"]

    tracking_seconds = sum(
        interval["duration_s"]
        for run in timeline
        for interval in run["qualified_tracking_intervals"]
    )
    tracking_percent = 100.0 * tracking_seconds / detection["current"]["rf_seconds"]
    pooled_positive = sum(item["positive"] for item in historical)
    pooled_visits = sum(item["visits"] for item in historical)

    summary = {
        "identity_caveat": (
            "Detector-positive pilot evidence is not independent proof of Starlink identity."
        ),
        "current_fpga_campaign": {
            "native_rate_sps": detection["sample_rate_sps"],
            "exported_acquisition_rate_sps": detection["exported_acquisition_rate_sps"],
            "rf_seconds": detection["current"]["rf_seconds"],
            "qualified_tracking_seconds": tracking_seconds,
            "qualified_tracking_time_percent": tracking_percent,
            "successful_dwells": detection["current"]["successful_dwells"],
            "dwell_count": detection["current"]["dwell_count"],
            "dwell_hit_percent": 100.0 * detection["current"]["dwell_success_fraction"],
            "timeline": timeline,
        },
        "earlier_same_handoff_detector": {
            "successful_dwells": detection["previous_comparable_scan64"]["successful_dwells"],
            "dwell_count": detection["previous_comparable_scan64"]["dwell_count"],
            "dwell_hit_percent": 100.0
            * detection["previous_comparable_scan64"]["dwell_success_fraction"],
        },
        "historical_2p5_msps_lightweight_scanner": {
            "runs": historical,
            "pooled_positive": pooled_positive,
            "pooled_visits": pooled_visits,
            "pooled_positive_visit_percent": 100.0 * pooled_positive / pooled_visits,
            "comparability": (
                "These 120-ms visits hop across eight targets and use a lightweight "
                "positive-only detector. They are not equivalent to a four-pilot FPGA handoff."
            ),
        },
    }
    (HERE / "signal-detection-duty-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    fig, axes = plt.subplots(2, 1, figsize=(12, 9), layout="constrained")

    for row, run in enumerate(timeline):
        axes[0].broken_barh([(0, run["duration_s"])], (row - 0.28, 0.56), facecolors="0.88")
        for interval in run["qualified_tracking_intervals"]:
            axes[0].broken_barh(
                [(interval["start_s"], interval["duration_s"])],
                (row - 0.28, 0.56),
                facecolors="#009E73",
            )
        axes[0].scatter(
            run["handoff_times_s"],
            [row] * len(run["handoff_times_s"]),
            marker="*",
            s=150,
            color="#E69F00",
            edgecolor="black",
            linewidth=0.6,
            zorder=4,
        )
    axes[0].set_yticks(range(len(timeline)), [run["name"] for run in timeline])
    axes[0].invert_yaxis()
    axes[0].set(
        title="Qualified detector state through the five 30-MS/s FPGA recordings",
        xlabel="Elapsed recording time (s)",
        ylabel="Recording",
        xlim=(0, 300),
    )
    axes[0].grid(axis="x", alpha=0.2)
    axes[0].text(
        0.99,
        0.05,
        "green = native tracking after qualified handoff\n"
        "star = handoff; grey = scanning / no qualified track",
        transform=axes[0].transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "0.8", "alpha": 0.92},
    )

    labels = [
        "Current FPGA\ntracking time",
        "Current dwells\nwith handoff",
        "Earlier same-detector\ndwells with handoff",
        *[item["name"].replace(" ", "\n", 2) + "\npositive visits" for item in historical],
        *[item["name"].replace(" ", "\n", 2) + "\ncapture duty" for item in historical],
    ]
    values = [
        tracking_percent,
        100.0 * detection["current"]["dwell_success_fraction"],
        100.0 * detection["previous_comparable_scan64"]["dwell_success_fraction"],
        *[item["positive_visit_percent"] for item in historical],
        *[item["capture_duty_percent"] for item in historical],
    ]
    colors = [
        "#009E73",
        "#E69F00",
        "#E69F00",
        *("#0072B2" for _ in historical),
        *("0.55" for _ in historical),
    ]
    bars = axes[1].bar(range(len(values)), values, color=colors)
    axes[1].set(
        title="Different duty denominators: only like-for-like percentages are comparable",
        ylabel="Percent",
        ylim=(0, 105),
    )
    axes[1].set_xticks(range(len(labels)), labels, fontsize=8)
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].bar_label(bars, labels=[f"{value:.2f}%" for value in values], padding=3, fontsize=8)
    axes[1].text(
        0.99,
        0.49,
        "blue = lightweight detector-positive 120-ms visits\n"
        "grey = valid-IQ capture duty; orange = dwell hit rate",
        transform=axes[1].transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "0.8", "alpha": 0.92},
    )
    fig.savefig(HERE / "signal-detection-duty-comparison.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
