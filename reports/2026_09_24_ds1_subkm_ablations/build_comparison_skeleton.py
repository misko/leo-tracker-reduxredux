#!/usr/bin/env python3
# ruff: noqa: E501
"""Build the merge-safe DS1 technique-audit comparison skeleton.

No inference occurs here.  It combines sealed DS1 controls with the separately
scoped, exact historical timing rows and makes every unsupported technique
explicit rather than disappearing from the comparison table.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
DS1 = HERE.parent / "2026_09_24_ds1"

METHODS = {
    "ds1_tau_zero": "Sealed DS1 blind pointwise association, tau=0",
    "ds1_shared_tau": "Sealed DS1 blind pointwise association, one shared bounded tau",
    "fixed_identity_tau_zero_control": "TRAIN-only tau-zero ID freeze on DS1 trace",
    "linearized_scan_epoch_scale1_sensitivity": "Diagnostic cached-state first-order scan epochs, scale 1 s",
    "linearized_norad_rate": "Diagnostic cached-state first-order recurrent-NORAD age-rate correction",
    "fixed_scale_robust_rate_sensitivity": "Diagnostic rate sensitivity; fixed 250 Hz robust weights, not a likelihood ablation",
    "exact_historical_timing_fixed_id": "Sealed nonlinear historical timing fit, fixed IDs/local optimizer; conditional",
    "fractional_track_time": "Historical per-track timing; not transferable with current timing authority",
    "dual_rx_beam_geometry": "Requires calibrated dual-RX and beam/visibility evidence absent from scalar DS1 cache",
}


def main():
    dataset = json.loads((DS1 / "dataset.json").read_text())
    evaluation = json.loads((DS1 / "evaluation.json").read_text())["rows"]
    historical = json.loads((HERE / "historical_exact_timing_rows.json").read_text())["rows"]
    control = {(r["case_id"], r["prior"], r["model"]): r for r in evaluation}
    rows = []
    for case in dataset["cases"]:
        for prior in dataset["priors"]:
            common = {
                key: case[key] for key in ("case_id", "partition", "group_id", "view", "scan_count")
            }
            common["prior"] = prior
            for method, ds1_model in (
                ("ds1_tau_zero", "baseline"),
                ("ds1_shared_tau", "shared_time"),
            ):
                source = control[case["case_id"], prior, ds1_model]
                rows.append(
                    {
                        **common,
                        "method": method,
                        "status": source["status"],
                        "reason": source.get("failure", {}).get("reason"),
                        "reference_error_km": source.get("reference_error_km"),
                        "held_capped_rms_hz": source.get("held_capped_rms_hz"),
                        "held_uncapped_rms_hz": source.get("held_uncapped_supported_rms_hz"),
                        "scope": "DS1 frozen blind trace",
                        "source": "reports/2026_09_24_ds1/evaluation.json",
                    }
                )
            for method, reason in (
                (
                    "fixed_identity_tau_zero_control",
                    "pending matched rerun after corrected tau-zero ID definition",
                ),
                (
                    "linearized_scan_epoch_scale1_sensitivity",
                    "pending diagnostic only; not the sealed nonlinear 0.2/1/5 s model",
                ),
                (
                    "linearized_norad_rate",
                    "pending diagnostic only; lacks historical exact/quartic phase-state gate",
                ),
                (
                    "fixed_scale_robust_rate_sensitivity",
                    "pending sensitivity only; selection objective differs from formal likelihood",
                ),
                (
                    "fractional_track_time",
                    "not applicable: historical support exceeded present timing authority and failed another group",
                ),
                (
                    "dual_rx_beam_geometry",
                    "not applicable: no calibrated dual-RX/beam evidence in scalar DS1 cache",
                ),
            ):
                status = (
                    "not_applicable"
                    if method in ("fractional_track_time", "dual_rx_beam_geometry")
                    else "pending"
                )
                rows.append(
                    {
                        **common,
                        "method": method,
                        "status": status,
                        "reason": reason,
                        "scope": "DS1 frozen blind trace",
                        "source": None,
                    }
                )
    for source in historical:
        case = next((x for x in dataset["cases"] if x["case_id"] == source["case_id"]), None)
        if case is None:
            continue
        rows.append(
            {
                **{
                    key: case[key]
                    for key in ("case_id", "partition", "group_id", "view", "scan_count")
                },
                "prior": source["prior"],
                "method": "exact_historical_timing_fixed_id",
                "status": "completed_conditional"
                if source["status"] == "completed"
                else source["status"],
                "reason": source["comparison_scope"],
                "reference_error_km": source["reference_error_km"],
                "held_capped_rms_hz": source["held_capped_rms_hz"],
                "held_uncapped_rms_hz": source["held_uncapped_rms_hz"],
                "scope": source["comparison_scope"],
                "source": source["source"],
                "exact_model": source["model"],
                "scale_s": source["scale_s"],
                "tau_s": source["tau_s"],
                "tau_boundary_count": source["tau_boundary_count"],
            }
        )
    fields = sorted({key for row in rows for key in row})
    with (HERE / "comparison_skeleton.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter((row["method"], row["status"]) for row in rows)
    summary = [
        {"method": m, "status": s, "rows": n, "definition": METHODS[m]}
        for (m, s), n in sorted(counts.items())
    ]
    payload = {
        "schema": "ds1-technique-audit-skeleton/v1",
        "rows": rows,
        "method_definitions": METHODS,
        "summary": summary,
        "truth_used_for_fit": False,
        "held_used_for_fit": False,
    }
    (HERE / "comparison_skeleton.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    controls = [
        r
        for r in rows
        if r["method"] in ("ds1_tau_zero", "ds1_shared_tau") and r["status"] == "completed"
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for method in ("ds1_tau_zero", "ds1_shared_tau"):
        values = [r for r in controls if r["method"] == method]
        axes[0].scatter(
            range(len(values)), [r["reference_error_km"] for r in values], s=16, label=method
        )
        axes[1].scatter(
            [r["held_capped_rms_hz"] for r in values],
            [r["reference_error_km"] for r in values],
            s=16,
            label=method,
        )
    for axis in axes:
        axis.axhline(1, color="black", linewidth=1, linestyle="--")
        axis.set_yscale("log")
        axis.legend(fontsize=8)
    axes[0].set(title="Sealed DS1 controls", xlabel="completed arm", ylabel="post-seal error (km)")
    axes[1].set(title="Held RMS does not rank location", xlabel="held capped RMS (Hz)")
    fig.tight_layout()
    fig.savefig(HERE / "ds1_control_comparison.png", dpi=180)
    plt.close(fig)
    exact = [
        r
        for r in rows
        if r["method"] == "exact_historical_timing_fixed_id"
        and r["status"] == "completed_conditional"
    ]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for model in sorted({r["exact_model"] for r in exact}):
        values = [r for r in exact if r["exact_model"] == model]
        ax.scatter(
            [r["held_capped_rms_hz"] for r in values],
            [r["reference_error_km"] for r in values],
            s=14,
            label=model,
        )
    ax.axhline(1, color="black", linewidth=1, linestyle="--")
    ax.set_yscale("log")
    ax.set(
        title="Exact historical timing arms: conditional scope",
        xlabel="held capped RMS (Hz)",
        ylabel="post-seal error (km)",
    )
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(HERE / "historical_exact_timing_held_error.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
