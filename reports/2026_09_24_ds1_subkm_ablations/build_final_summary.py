#!/usr/bin/env python3
# ruff: noqa: E501
"""Build the compact, provenance-linked DS1 technique comparison."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def _read(name: str) -> dict:
    return json.loads((REPORTS / name).read_text())


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _completed(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("status") == "completed"]


def build() -> dict:
    ds1 = _read("2026_09_24_ds1/evaluation.json")
    timing = _read("2026_09_24_ds1_timing_ablations/timing_rows.json")
    fractional = _read("2026_09_24_ds1_timing_ablations/fractional_per_track_evaluation.json")
    orbit = _read("2026_09_24_ds1_orbit_arm/summary.json")

    rows: list[dict] = []
    ds1_rows = _completed(ds1["rows"])
    for model, label in (
        ("baseline", "Ordinary Doppler baseline"),
        ("shared_time", "Shared global receive-time shift"),
    ):
        selected = [row for row in ds1_rows if row["model"] == model]
        full = [row for row in selected if row["view"] == "all"]
        rows.append(
            {
                "method": label,
                "method_id": model,
                "qualification": "primary_ds1",
                "coverage": "38 completed case/prior fits; 4 explicit TEST64 failures",
                "train_error_km": _median(
                    [row["reference_error_km"] for row in selected if row["partition"] == "train"]
                ),
                "validation_error_km": _median(
                    [
                        row["reference_error_km"]
                        for row in selected
                        if row["partition"] == "validation"
                    ]
                ),
                "test_error_km": _median(
                    [row["reference_error_km"] for row in selected if row["partition"] == "test"]
                ),
                "full_block_error_km": _median([row["reference_error_km"] for row in full]),
                "sub_km_validation": False,
                "source": "reports/2026_09_24_ds1/evaluation.json",
                "interpretation": "Current blind DS1 comparison with TRAIN-only candidate selection.",
            }
        )

    timing_rows = _completed(timing["rows"])
    for model, label in (
        ("fixed_identity_shared_global_tau", "Fixed-ID shared timing (scale 5 s)"),
        ("regularized_global_plus_scan_epoch", "Fixed-ID regularized per-scan epoch (scale 5 s)"),
    ):
        selected = [
            row
            for row in timing_rows
            if row["model"] == model and row["scale_s"] == 5.0 and row["view"] == "all"
        ]
        rows.append(
            {
                "method": label,
                "method_id": model,
                "qualification": "conditional_fixed_identity",
                "coverage": "2 full TRAIN and 2 full validation blocks, both priors",
                "train_error_km": _median(
                    [
                        row["post_seal_reference_error_km"]
                        for row in selected
                        if row["partition"] == "train"
                    ]
                ),
                "validation_error_km": _median(
                    [
                        row["post_seal_reference_error_km"]
                        for row in selected
                        if row["partition"] == "validation"
                    ]
                ),
                "test_error_km": None,
                "full_block_error_km": _median(
                    [row["post_seal_reference_error_km"] for row in selected]
                ),
                "sub_km_validation": False,
                "source": "reports/2026_09_24_ds1_timing_ablations/timing_rows.json",
                "interpretation": "Exact historical local-search arm; identities are frozen from tau-zero fits.",
            }
        )

    frac_rows = [
        row for row in _completed(fractional["rows"]) if row["geographic_point_role"] == "shared"
    ]
    rows.append(
        {
            "method": "Independent fractional per-track timing",
            "method_id": "fractional_per_track_tau",
            "qualification": "diagnostic_fixed_points",
            "coverage": "Four 16-scan non-TEST groups, both priors; inherited terminal points",
            "train_error_km": _median(
                [row["reference_error_km"] for row in frac_rows if row["partition"] == "train"]
            ),
            "validation_error_km": _median(
                [row["reference_error_km"] for row in frac_rows if row["partition"] == "validation"]
            ),
            "test_error_km": None,
            "full_block_error_km": None,
            "sub_km_validation": False,
            "source": "reports/2026_09_24_ds1_timing_ablations/fractional_per_track_evaluation.json",
            "interpretation": "Diagnostic only: no geographic re-search and 3-10% of track shifts hit +/-5 s.",
        }
    )

    orbit_rows = orbit["rows"]
    rows.append(
        {
            "method": "Causal per-NORAD phase rate (exact SGP4)",
            "method_id": "causal_per_norad_phase_rate",
            "qualification": "bounded_feasibility",
            "coverage": "Two singleton cases, both priors; deterministic top-1/top-4 pair subsets",
            "train_error_km": _median(
                [row["reference_error_km"] for row in orbit_rows if row["partition"] == "train"]
            ),
            "validation_error_km": _median(
                [
                    row["reference_error_km"]
                    for row in orbit_rows
                    if row["partition"] == "validation"
                ]
            ),
            "test_error_km": None,
            "full_block_error_km": None,
            "sub_km_validation": False,
            "source": "reports/2026_09_24_ds1_orbit_arm/summary.json",
            "interpretation": "Converged and exact-gated, but it did not move the selected geographic point.",
        }
    )

    rows.extend(
        [
            {
                "method": "Formal causal orbit model, fixed-ID transfer control",
                "method_id": "formal_orbit_fixed_id_first6",
                "qualification": "negative_transfer_control",
                "coverage": "First six scans of both TRAIN groups",
                "train_error_km": 8.395,
                "validation_error_km": None,
                "test_error_km": None,
                "full_block_error_km": None,
                "sub_km_validation": False,
                "source": "reports/2026_09_23_train_orbit_uncertainty_design/FINDINGS.md",
                "interpretation": "Errors were 12.025/12.029 km on one group and 4.764 km on the other.",
            },
            {
                "method": "Configured-site orbit calibration",
                "method_id": "configured_site_orbit_calibration",
                "qualification": "disqualified_truth_leakage",
                "coverage": "Not run as a DS1 accuracy arm",
                "train_error_km": None,
                "validation_error_km": None,
                "test_error_km": None,
                "full_block_error_km": None,
                "sub_km_validation": False,
                "source": "reports/2026_09_24_ds1_subkm_ablations/technique_matrix.json",
                "interpretation": "Historical 292 m used configured-site calibration; corrected error is 1.579 km.",
            },
            {
                "method": "16-scan exposed candidate/seed search",
                "method_id": "sixteen_scan_joint_conditional",
                "qualification": "disqualified_evaluation_exposure",
                "coverage": "Not imported into DS1",
                "train_error_km": None,
                "validation_error_km": None,
                "test_error_km": None,
                "full_block_error_km": None,
                "sub_km_validation": False,
                "source": "reports/2026_09_24_ds1_subkm_ablations/technique_matrix.json",
                "interpretation": "Historical 314 m depended on evaluation-exposed candidates and seeds.",
            },
            {
                "method": "Dual-LNB GLRT-margin beam proxy",
                "method_id": "dual_lnb_beam_proxy",
                "qualification": "disqualified_shuffled_control",
                "coverage": "Not imported into DS1",
                "train_error_km": None,
                "validation_error_km": None,
                "test_error_km": None,
                "full_block_error_km": None,
                "sub_km_validation": False,
                "source": "reports/2026_09_24_ds1_subkm_ablations/technique_matrix.json",
                "interpretation": "Historical 347.7 m was beaten by shuffled controls.",
            },
            {
                "method": "Native RX1 receiver reference",
                "method_id": "native_rx1_receiver_reference",
                "qualification": "disqualified_numerical_uncertainty",
                "coverage": "Not imported into DS1",
                "train_error_km": None,
                "validation_error_km": None,
                "test_error_km": None,
                "full_block_error_km": None,
                "sub_km_validation": False,
                "source": "reports/2026_09_24_ds1_subkm_ablations/technique_matrix.json",
                "interpretation": "Historical 897.9 m failed numerical and uncertainty checks.",
            },
        ]
    )

    return {
        "schema": "ds1-subkm-technique-evaluation/v1",
        "conclusion": "No qualified method reaches sub-kilometre error on DS1 validation.",
        "reference_used_for_fit": False,
        "held_used_for_fit": False,
        "rows": rows,
    }


def render(summary: dict) -> None:
    rows = summary["rows"]
    (HERE / "evaluation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fields = list(rows[0])
    with (HERE / "evaluation_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    plotted = [
        row
        for row in rows
        if row["train_error_km"] is not None and row["validation_error_km"] is not None
    ]
    labels = [row["method"] for row in plotted]
    y = list(range(len(plotted)))
    fig, ax = plt.subplots(figsize=(11, 5.8))
    ax.scatter([row["train_error_km"] for row in plotted], y, marker="o", label="TRAIN")
    ax.scatter([row["validation_error_km"] for row in plotted], y, marker="s", label="Validation")
    ax.axvline(1.0, color="tab:red", linestyle="--", linewidth=1.2, label="1 km target")
    ax.set_yticks(y, labels)
    ax.set_xlabel("Median reference-position error (km)")
    ax.set_title(
        "DS1 sub-kilometre technique audit\nMatched coverage differs; see qualification table"
    )
    ax.grid(axis="x", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "technique_vs_ds1.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    render(build())
