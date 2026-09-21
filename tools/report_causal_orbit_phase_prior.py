"""Render the sealed causal phase-prior experiment and separate reference evaluation."""

import argparse
import json
import shutil
from pathlib import Path

import matplotlib
import numpy as np
from replay_regional_doppler import digest, write_json
from report_orbit_clock_stability import horizontal_error

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def find_model(rows, orbit, clock="shared_recorded", selection="all"):
    return next(
        row
        for row in rows
        if row["orbit_model"] == orbit
        and row["clock_model"] == clock
        and row["selection"] == selection
    )


def percent(value):
    return 100 * value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--retrospective", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-lat", type=float, required=True)
    parser.add_argument("--reference-lon", type=float, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    analysis = json.loads(args.analysis.read_text())
    retrospective = json.loads(args.retrospective.read_text())
    if not analysis["strictly_causal"] or analysis["evaluation_location_used"]:
        raise ValueError("sealed causal inference required")
    reference = {
        "latitude_deg": args.reference_lat,
        "longitude_deg": args.reference_lon,
    }
    rows = []
    for model in analysis["models"]:
        rows.append({**model, "horizontal_error_m": horizontal_error(model, reference)})
    for model in retrospective["models"]:
        if model["clock_model"] in {"fixed", "shared_recorded"}:
            rows.append(
                {
                    **model,
                    "orbit_model": "full_future_tle",
                    "horizontal_error_m": horizontal_error(model, reference),
                }
            )
    diagnostic = analysis["future_tle_diagnostic"]
    baseline_mismatch = np.asarray([row["baseline_future_tle_mismatch_hz"] for row in diagnostic])
    corrected_mismatch = np.asarray([row["corrected_future_tle_mismatch_hz"] for row in diagnostic])
    predicted_phase = np.asarray([row["predicted_phase_s"] for row in diagnostic])
    future_phase = np.asarray([row["future_fitted_phase_s"] for row in diagnostic])
    strict = find_model(rows, "baseline")
    causal = find_model(rows, "causal_phase_prior")
    oracle = find_model(rows, "future_tle_oracle_phase")
    future = find_model(rows, "full_future_tle")
    position_gap = strict["horizontal_error_m"] - future["horizontal_error_m"]
    rms_gap = strict["evaluation_rms_hz"] - future["evaluation_rms_hz"]
    summary = {
        "analysis_digest_before_reference_evaluation": digest(args.analysis),
        "reference_used_only_after_inference": reference,
        "models": rows,
        "future_tle_diagnostic": {
            "episodes": len(diagnostic),
            "median_mismatch_before_hz": float(np.median(baseline_mismatch)),
            "median_mismatch_after_hz": float(np.median(corrected_mismatch)),
            "pooled_squared_mismatch_reduction": float(
                1 - np.sum(corrected_mismatch**2) / np.sum(baseline_mismatch**2)
            ),
            "fraction_episodes_improved": float(np.mean(corrected_mismatch < baseline_mismatch)),
            "phase_correlation": float(np.corrcoef(predicted_phase, future_phase)[0, 1]),
            "median_absolute_oracle_phase_s": float(np.median(abs(future_phase))),
            "median_absolute_phase_error_s": float(np.median(abs(future_phase - predicted_phase))),
            "squared_phase_error_reduction": float(
                1 - np.sum((future_phase - predicted_phase) ** 2) / np.sum(future_phase**2)
            ),
        },
        "all_shared_clock": {
            "strict_position_error_m": strict["horizontal_error_m"],
            "causal_prior_position_error_m": causal["horizontal_error_m"],
            "oracle_phase_position_error_m": oracle["horizontal_error_m"],
            "full_future_tle_position_error_m": future["horizontal_error_m"],
            "causal_fraction_of_future_position_gap_recovered": (
                strict["horizontal_error_m"] - causal["horizontal_error_m"]
            )
            / position_gap,
            "oracle_phase_fraction_of_future_position_gap_recovered": (
                strict["horizontal_error_m"] - oracle["horizontal_error_m"]
            )
            / position_gap,
            "strict_heldout_rms_hz": strict["evaluation_rms_hz"],
            "causal_prior_heldout_rms_hz": causal["evaluation_rms_hz"],
            "oracle_phase_heldout_rms_hz": oracle["evaluation_rms_hz"],
            "full_future_tle_heldout_rms_hz": future["evaluation_rms_hz"],
            "causal_fraction_of_future_rms_gap_recovered": (
                strict["evaluation_rms_hz"] - causal["evaluation_rms_hz"]
            )
            / rms_gap,
            "causal_squared_rf_residual_reduction": 1
            - (causal["evaluation_rms_hz"] / strict["evaluation_rms_hz"]) ** 2,
        },
    }
    shutil.copyfile(args.analysis, args.output / "analysis.json")
    write_json(args.output / "evaluation.json", summary)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    candidates = analysis["frozen_model"]["candidates"]
    labels = [
        row["name"] if row.get("alpha") is None else f"ridge {row['alpha']:g}" for row in candidates
    ]
    values = [1e3 * row["validation_median_absolute_rate_error_s_h"] for row in candidates]
    axes[0, 0].bar(np.arange(len(labels)), values, color="tab:blue")
    axes[0, 0].set(
        xticks=np.arange(len(labels)),
        xticklabels=labels,
        ylabel="Median absolute phase-rate error (ms/h)",
        title="Pre-target temporal validation (446 satellites)",
    )
    axes[0, 0].tick_params(axis="x", rotation=35)
    axes[0, 0].grid(axis="y", alpha=0.25)

    correlation = np.corrcoef(predicted_phase, future_phase)[0, 1]
    axes[0, 1].scatter(future_phase, predicted_phase, s=10, alpha=0.45)
    limit = [min(future_phase.min(), predicted_phase.min()), max(future_phase.max(), 1)]
    axes[0, 1].plot(limit, limit, "k--", lw=1, label="Perfect prediction")
    axes[0, 1].set(
        xlim=limit,
        ylim=limit,
        xlabel="Later-TLE fitted phase (s; diagnostic only)",
        ylabel="Pre-capture prediction (s)",
        title=f"Individual phase prediction: r={correlation:.2f}",
    )
    axes[0, 1].legend()
    axes[0, 1].grid(alpha=0.25)

    improved_percent = percent(np.mean(corrected_mismatch < baseline_mismatch))
    axes[1, 0].scatter(baseline_mismatch, corrected_mismatch, s=10, alpha=0.45)
    upper = max(baseline_mismatch.max(), corrected_mismatch.max())
    axes[1, 0].plot([1, upper], [1, upper], "k--", lw=1)
    axes[1, 0].set(
        xscale="log",
        yscale="log",
        xlabel="Original mismatch to later TLE (Hz)",
        ylabel="After causal phase prior (Hz)",
        title=f"Later-TLE diagnostic: {improved_percent:.0f}% of episodes improve",
    )
    axes[1, 0].grid(alpha=0.25)

    display = [strict, causal, oracle, future]
    display_labels = ["Strict", "Causal prior", "Oracle phase", "Full later TLE"]
    x = np.arange(len(display))
    bars = axes[1, 1].bar(
        x - 0.18,
        [row["horizontal_error_m"] / 1000 for row in display],
        0.36,
        color="tab:blue",
        label="Position error",
    )
    axes[1, 1].bar_label(bars, fmt="%.2f", fontsize=8)
    right = axes[1, 1].twinx()
    right.plot(
        x + 0.18,
        [row["evaluation_rms_hz"] for row in display],
        "o-",
        color="tab:orange",
        label="Held-out RMS",
    )
    axes[1, 1].set(
        xticks=x,
        xticklabels=display_labels,
        ylabel="Horizontal error (km)",
        title="All tracks, bounded shared receiver clock",
    )
    right.set_ylabel("Randomized held-out RMS (Hz)")
    axes[1, 1].grid(axis="y", alpha=0.25)
    handles, names = axes[1, 1].get_legend_handles_labels()
    other_handles, other_names = right.get_legend_handles_labels()
    axes[1, 1].legend(handles + other_handles, names + other_names, fontsize=8)
    fig.suptitle(
        "How much orbital phase error can pre-capture modelling remove?\n"
        "Future TLE and known receiver coordinate are evaluation-only"
    )
    fig.savefig(args.output / "summary.png", dpi=170)
    plt.close(fig)
    print(json.dumps(summary["all_shared_clock"], indent=2))


if __name__ == "__main__":
    main()
