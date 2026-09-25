#!/usr/bin/env python3
# ruff: noqa: E501
"""Build the DS1 iteration progress audit from frozen report artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def source(path: str) -> dict[str, str]:
    full = ROOT / path
    if not full.is_file():
        raise FileNotFoundError(full)
    return {
        "path": path,
        "sha256": hashlib.sha256(full.read_bytes()).hexdigest(),
    }


ROWS = [
    (
        1,
        "Shared-time DS1 benchmark",
        3.364,
        1.996,
        4.134,
        "aggregate",
        "benchmark",
        "Median of eight completed full-block/start results; not one sequential estimate.",
        "reports/2026_09_24_ds1/REPORT.md",
    ),
    (
        2,
        "Local geographic refinement",
        3.912,
        1.689,
        6.055,
        "aggregate",
        "development",
        "Median and range of four prefix-6 global-time arms; one-scan arms excluded from this summary.",
        "reports/2026_09_24_ds1_iteration2/REPORT.md",
    ),
    (
        3,
        "Joint tau/rate screening",
        3.011790,
        0.634774,
        4.260024,
        "aggregate",
        "invalid",
        "Mean/range of four overlapping development views; later convergence audit found all four selected fits nonconverged.",
        "reports/2026_09_24_ds1_joint_rate_search/iteration3-postseal/iteration3-postseal.json",
    ),
    (
        4,
        "Seed-union exact selection",
        2.313292,
        0.422928,
        4.203656,
        "aggregate",
        "development",
        "Mean/range of two group-specific estimates; not a shared-coordinate estimate.",
        "reports/2026_09_24_ds1_joint_rate_search/iteration4-postseal/iteration4-postseal.json",
    ),
    (
        5,
        "Timing refinement",
        2.725182,
        1.730384,
        3.719981,
        "aggregate",
        "development",
        "Mean/range of two group-specific estimates; one group improved and one regressed.",
        "reports/2026_09_24_ds1_joint_rate_search/iteration5-postseal/iteration5-postseal.json",
    ),
    (
        6,
        "Expanded exact shortlist",
        1.789851,
        0.422928,
        3.156774,
        "aggregate",
        "development",
        "Mean/range of two group-specific estimates; still not one shared coordinate.",
        "reports/2026_09_24_ds1_joint_rate_search/iteration6-postseal/iteration6-postseal.json",
    ),
    (
        7,
        "Residual likelihood ablation",
        1.789851,
        0.422928,
        3.156774,
        "aggregate",
        "no_gain",
        "Gaussian arm retained iteration-6 geography; robust arm was worse in one group.",
        "reports/2026_09_24_ds1_joint_rate_search/iteration7-postseal/iteration7-postseal.json",
    ),
    (
        8,
        "Joint shared coordinate",
        1.359305,
        None,
        None,
        "point",
        "development",
        "First result in the directly comparable shared-coordinate sequence.",
        "reports/2026_09_24_ds1_iteration8_joint_groups/REPORT.md",
    ),
    (
        9,
        "Joint local refinement",
        1.242891,
        None,
        None,
        "point",
        "development",
        "Reference-free selected shared coordinate; development corpus.",
        "reports/2026_09_24_ds1_iteration9_joint_refinement/REPORT.md",
    ),
    (
        10,
        "Finer joint refinement",
        1.179286,
        None,
        None,
        "point",
        "development",
        "Reference-free selected shared coordinate; development corpus.",
        "reports/2026_09_24_ds1_iteration10_refinement/REPORT.md",
    ),
    (
        11,
        "Fine confirmation",
        1.212614,
        None,
        None,
        "point",
        "no_gain",
        "Fine-grid selected result was slightly worse than iteration 10.",
        "reports/2026_09_24_ds1_iteration11_fine_confirmation/REPORT.md",
    ),
    (
        12,
        "Expanded/session-scale basin",
        0.787188,
        None,
        None,
        "point",
        "invalidated",
        "Historical sub-km development result; later rate-bound audit invalidated its qualification.",
        "reports/2026_09_24_ds1_iteration12_session_scale/REPORT.md",
    ),
    (
        13,
        "Basin closure",
        0.599900,
        None,
        None,
        "point",
        "invalidated",
        "Historically qualified; iteration 19 found the inherited rate-bound detector defective.",
        "reports/2026_09_24_ds1_iteration13_basin_closure/REPORT.md",
    ),
    (
        14,
        "Raw cap-800 basin",
        0.488151,
        None,
        None,
        "point",
        "diagnostic",
        "Terminal boundary point only; explicitly not a position estimate.",
        "reports/2026_09_24_ds1_iteration14_cap800_basin/REPORT.md",
    ),
    (
        15,
        "Information-weighted basin",
        0.575577,
        None,
        None,
        "point",
        "invalidated",
        "Historical best qualified claim; explicitly rejected by iteration 19.",
        "reports/2026_09_25_ds1_iteration19_rate_bound_audit/REPORT.md",
    ),
    (
        16,
        "Dynamic association",
        0.859630,
        None,
        None,
        "point",
        "diagnostic",
        "Unqualified terminal boundary point.",
        "reports/2026_09_24_ds1_iteration16_dynamic_association/REPORT.md",
    ),
    (
        17,
        "Reacquire then freeze",
        0.662549,
        None,
        None,
        "point",
        "invalidated",
        "Originally qualified, but its persisted rates include values within optimizer tolerance of the old ±0.25 guard; it has not passed the corrected gate.",
        "reports/2026_09_24_ds1_iteration17_reacquire_then_freeze/inference.json",
    ),
    (
        18,
        "Timing refresh",
        0.884064,
        None,
        None,
        "point",
        "diagnostic",
        "Unqualified terminal boundary point.",
        "reports/2026_09_24_ds1_iteration18_timing_refresh/REPORT.md",
    ),
    (
        19,
        "Rate-bound audit",
        0.910457,
        None,
        None,
        "point",
        "audit",
        "Correctly invalidated iteration 15; widened-rate basin remained open and this value is diagnostic only.",
        "reports/2026_09_25_ds1_iteration19_rate_bound_audit/REPORT.md",
    ),
    (
        20,
        "Session-balanced zero-rate",
        0.267450,
        None,
        None,
        "point",
        "diagnostic",
        "Very close terminal boundary point, but the objective was still descending; not a position estimate.",
        "reports/2026_09_25_ds1_iteration20_session_predictive/REPORT.md",
    ),
    (
        21,
        "Closure extension",
        0.713795,
        None,
        None,
        "point",
        "diagnostic",
        "Selected terminal boundary error; closest visited point was 0.172805 km but was not RF-selected and is not plotted as an estimate.",
        "reports/2026_09_25_ds1_iteration21_session_balanced_closure/REPORT.md",
    ),
    (
        22,
        "Randomized-time predictive scorer",
        None,
        None,
        None,
        "none",
        "model_progress",
        "No geographic search. Rates improved randomized HELD loss in all 12 sessions, but four sources hit the old rate guard.",
        "reports/2026_09_25_ds1_iteration22_randomized_time_predictive/smoke.json",
    ),
    (
        23,
        "Widened-rate audit",
        None,
        None,
        None,
        "none",
        "no_go",
        "No geographic search. ±0.50 s/h failed its prospective gate; ±1 was diagnostic only.",
        "reports/2026_09_25_ds1_iteration23_widened_rate/smoke.json",
    ),
    (
        24,
        "Cross-fitted rate identifiability",
        None,
        None,
        None,
        "none",
        "no_go",
        "No geographic search. 65/80 eligible sources passed, but the universal prospective gate failed.",
        "reports/2026_09_25_ds1_iteration24_crossfit_rate/audit.json",
    ),
    (
        25,
        "Source admission",
        None,
        None,
        None,
        "none",
        "no_go",
        "No geographic search. HELD improved versus zero but regressed versus both all-source rate controls.",
        "reports/2026_09_25_ds1_iteration25_source_admission/evaluation.json",
    ),
    (
        26,
        "Rate marginalization",
        None,
        None,
        None,
        "none",
        "numerical_no_go",
        "No geographic search. Statistical smoke passed; a remote-mode quartic extrapolation failed the exact 0.2 Hz gate.",
        "reports/2026_09_25_ds1_iteration26_rate_marginal/smoke.json",
    ),
    (
        27,
        "Exact phase-state cache and sealed stencil",
        1.112841731176525,
        None,
        None,
        "point",
        "search_open",
        "Exact-cache smoke passed, but the southwest stencil boundary won and all 12 leave-one-session reranks agreed; unqualified diagnostic.",
        "reports/2026_09_25_ds1_iteration27_phase_cache/evaluation/postseal-evaluation.json",
    ),
]


def build_rows() -> list[dict]:
    rows = []
    for iteration, name, value, low, high, kind, status, note, path in ROWS:
        rows.append(
            {
                "iteration": iteration,
                "name": name,
                "postseal_geographic_error_km": value,
                "aggregate_min_km": low,
                "aggregate_max_km": high,
                "geographic_metric_kind": kind,
                "current_disposition": status,
                "note": note,
                "source": source(path),
            }
        )
    return rows


def render(rows: list[dict]) -> None:
    fig, (early, shared, timeline) = plt.subplots(
        3,
        1,
        figsize=(14, 11),
        gridspec_kw={"height_ratios": [1.0, 1.45, 0.72]},
        constrained_layout=True,
    )
    early_rows = rows[:7]
    x = [r["iteration"] for r in early_rows]
    y = [r["postseal_geographic_error_km"] for r in early_rows]
    lo = [v - r["aggregate_min_km"] for v, r in zip(y, early_rows, strict=True)]
    hi = [r["aggregate_max_km"] - v for v, r in zip(y, early_rows, strict=True)]
    early.errorbar(x, y, yerr=[lo, hi], marker="o", color="#607d8b", capsize=4)
    early.set_title(
        "Iterations 1–7: aggregate of different cases/groups (context only; not one position sequence)"
    )
    early.set_ylabel("Post-seal error (km)\nmean/median and range")
    early.set_xticks(x)
    early.grid(alpha=0.25)
    early.text(
        0.99,
        0.95,
        "Aggregation changes by iteration",
        transform=early.transAxes,
        ha="right",
        va="top",
        color="#455a64",
    )

    colors = {
        "development": "#1565c0",
        "no_gain": "#78909c",
        "invalidated": "#d32f2f",
        "diagnostic": "#ef6c00",
        "audit": "#6a1b9a",
        "search_open": "#ef6c00",
    }
    comparable = [r for r in rows if 8 <= r["iteration"] <= 21]
    shared.plot(
        [r["iteration"] for r in comparable],
        [r["postseal_geographic_error_km"] for r in comparable],
        color="#b0bec5",
        linewidth=1.2,
        zorder=1,
    )
    for row in comparable:
        shared.scatter(
            row["iteration"],
            row["postseal_geographic_error_km"],
            s=80,
            color=colors[row["current_disposition"]],
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
    final_row = rows[26]
    shared.scatter(
        final_row["iteration"],
        final_row["postseal_geographic_error_km"],
        s=100,
        color=colors[final_row["current_disposition"]],
        edgecolor="white",
        linewidth=0.8,
        zorder=3,
    )
    shared.axhline(1.0, color="#2e7d32", linestyle="--", linewidth=1, label="1 km target")
    shared.axvline(19, color="#6a1b9a", linestyle=":", linewidth=1.5)
    shared.annotate(
        "I19 corrected rate-bound audit",
        (19, 0.91),
        xytext=(16.2, 1.48),
        arrowprops={"arrowstyle": "->", "color": "#6a1b9a"},
        color="#6a1b9a",
    )
    shared.annotate(
        "0.267 km boundary diagnostic\nnot a position estimate",
        (20, 0.26745),
        xytext=(17.7, 0.08),
        arrowprops={"arrowstyle": "->", "color": "#ef6c00"},
        color="#ef6c00",
    )
    shared.annotate(
        "I27: 1.113 km\nSW boundary winner",
        (27, final_row["postseal_geographic_error_km"]),
        xytext=(23.4, 1.34),
        arrowprops={"arrowstyle": "->", "color": "#ef6c00"},
        color="#ef6c00",
    )
    shared.set_title("Iterations 8–27: shared-coordinate development and latest sealed stencil")
    shared.set_ylabel("Selected post-seal error (km)")
    shared.set_xticks(list(range(8, 22)) + [27])
    shared.set_xlim(7.4, 27.6)
    shared.set_ylim(0, 1.62)
    shared.grid(alpha=0.25)
    shared.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#1565c0",
                label="development result",
                markersize=8,
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#d32f2f",
                label="later invalidated",
                markersize=8,
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#ef6c00",
                label="unqualified diagnostic",
                markersize=8,
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#6a1b9a",
                label="audit",
                markersize=8,
            ),
            Line2D([0], [0], color="#2e7d32", linestyle="--", label="1 km target"),
        ],
        ncol=3,
        loc="upper right",
        fontsize=9,
    )

    late = rows[21:]
    status_y = {"model_progress": 3, "no_go": 2, "numerical_no_go": 1, "search_open": 0}
    status_color = {
        "model_progress": "#2e7d32",
        "no_go": "#ef6c00",
        "numerical_no_go": "#8e24aa",
        "search_open": "#ef6c00",
    }
    for row in late:
        yy = status_y[row["current_disposition"]]
        timeline.scatter(
            row["iteration"],
            yy,
            s=110,
            color=status_color[row["current_disposition"]],
            edgecolor="white",
        )
        timeline.text(
            row["iteration"], yy + 0.16, str(row["iteration"]), ha="center", va="bottom", fontsize=9
        )
    timeline.set_yticks(
        [0, 1, 2, 3],
        ["geographic search open", "numerical no-go", "model no-go", "positive model evidence"],
    )
    timeline.set_xticks(range(22, 28))
    timeline.set_xlim(21.5, 27.5)
    timeline.set_ylim(-0.35, 3.55)
    timeline.grid(axis="x", alpha=0.2)
    timeline.set_title("Iterations 22–27: model qualification and final geographic no-go")
    timeline.set_xlabel("DS1 iteration")

    fig.suptitle(
        "DS1 progress audit — geographic accuracy and model validation are separate", fontsize=16
    )
    fig.savefig(HERE / "ds1-iteration-progress.png", dpi=180)
    plt.close(fig)


def main() -> None:
    rows = build_rows()
    payload = {
        "schema": "ds1-iteration-progress/v1",
        "generated_from_existing_artifacts_only": True,
        "interpretation": {
            "qualified_sub_km_current": False,
            "historical_best_claim_km": 0.575577,
            "historical_best_claim_disposition": "invalidated by iteration 19 rate-bound audit",
            "closest_selected_unqualified_diagnostic_km": 0.267450,
            "closest_visited_postseal_only_km": 0.172805,
            "current_geographic_conclusion": "No current qualified sub-km DS1 estimate.",
            "progress_conclusion": "Yes in model validity: iteration 27 fixed the iteration-26 numerical blocker and exposed a stable southwest objective slope, but its geographic search remained open and produced no qualified improvement.",
        },
        "cross_cutting_provenance": [
            source("reports/2026_09_25_ds1_iteration19_rate_bound_audit/REPORT.md"),
            source("reports/2026_09_24_ds1_iteration17_reacquire_then_freeze/inference.json"),
            source("reports/2026_09_25_ds1_iteration27_phase_cache/smoke.json"),
            source("reports/2026_09_25_ds1_iteration27_phase_cache/stencil.json"),
            source("reports/2026_09_25_ds1_iteration27_phase_cache/REPORT.md"),
        ],
        "rows": rows,
    }
    (HERE / "progress.json").write_text(json.dumps(payload, indent=2) + "\n")
    columns = [
        "iteration",
        "name",
        "postseal_geographic_error_km",
        "aggregate_min_km",
        "aggregate_max_km",
        "geographic_metric_kind",
        "current_disposition",
        "note",
        "source_path",
        "source_sha256",
    ]
    with (HERE / "progress.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            flat = {k: row.get(k) for k in columns[:-2]}
            flat["source_path"] = row["source"]["path"]
            flat["source_sha256"] = row["source"]["sha256"]
            writer.writerow(flat)
    render(rows)


if __name__ == "__main__":
    main()
