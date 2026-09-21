"""Evaluate and plot sealed joint causal orbit-phase uncertainty fits."""

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uncertainty", type=Path, required=True)
    parser.add_argument("--point-evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-lat", type=float, required=True)
    parser.add_argument("--reference-lon", type=float, required=True)
    args = parser.parse_args()
    uncertainty = json.loads(args.uncertainty.read_text())
    point = json.loads(args.point_evaluation.read_text())
    if not uncertainty["strictly_causal"] or uncertainty["evaluation_location_used"]:
        raise ValueError("sealed causal uncertainty fit required")
    reference = {"latitude_deg": args.reference_lat, "longitude_deg": args.reference_lon}

    def error(row):
        return horizontal_error(row, reference)

    uncertainty_rows = [{**row, "horizontal_error_m": error(row)} for row in uncertainty["results"]]
    stability = [{**row, "horizontal_error_m": error(row)} for row in uncertainty["stability"]]
    sensitivity = [
        {**row, "horizontal_error_m": error(row)} for row in uncertainty["prior_scale_sensitivity"]
    ]
    point_rows = point["models"]

    def model(orbit, clock="fixed"):
        return next(
            row
            for row in point_rows
            if row["selection"] == "all"
            and row["orbit_model"] == orbit
            and row["clock_model"] == clock
        )

    strict = model("baseline")
    causal_point = model("causal_phase_prior")
    oracle = model("future_tle_oracle_phase")
    future = model("full_future_tle")
    repeated = next(row for row in uncertainty_rows if row["mode"] == "repeated_satellites")
    flexible = next(
        row for row in uncertainty_rows if row["mode"] == "all_satellites_flexibility_control"
    )
    summary = {
        "uncertainty_digest_before_reference_evaluation": digest(args.uncertainty),
        "point_evaluation_digest": digest(args.point_evaluation),
        "reference_used_only_after_inference": reference,
        "results": uncertainty_rows,
        "stability": stability,
        "prior_scale_sensitivity": sensitivity,
        "baseline_fixed_clock": {
            "horizontal_error_m": strict["horizontal_error_m"],
            "heldout_rms_hz": strict["evaluation_rms_hz"],
        },
        "repeated_satellite_fraction_position_distance_removed": 1
        - repeated["horizontal_error_m"] / strict["horizontal_error_m"],
        "repeated_satellite_fraction_squared_rf_residual_removed": 1
        - (repeated["evaluation_rms_hz"] / strict["evaluation_rms_hz"]) ** 2,
        "all_satellite_fraction_position_distance_removed": 1
        - flexible["horizontal_error_m"] / strict["horizontal_error_m"],
        "all_satellite_fraction_squared_rf_residual_removed": 1
        - (flexible["evaluation_rms_hz"] / strict["evaluation_rms_hz"]) ** 2,
    }
    shutil.copyfile(args.uncertainty, args.output / "uncertainty-analysis.json")
    write_json(args.output / "uncertainty-evaluation.json", summary)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout="constrained")
    display = [strict, causal_point, repeated, flexible, oracle, future]
    labels = ["Strict", "Point prior", "Repeated IDs", "All IDs", "Oracle phase", "Later TLE"]
    x = np.arange(len(display))
    bars = axes[0, 0].bar(
        x - 0.18,
        [row["horizontal_error_m"] / 1000 for row in display],
        0.36,
        color="tab:blue",
        label="Position error",
    )
    axes[0, 0].bar_label(bars, fmt="%.2f", fontsize=8)
    right = axes[0, 0].twinx()
    right.plot(
        x + 0.18,
        [row["evaluation_rms_hz"] for row in display],
        "o-",
        color="tab:orange",
        label="Held-out RMS",
    )
    axes[0, 0].set(
        xticks=x,
        xticklabels=labels,
        ylabel="Horizontal error (km)",
        title="Fixed UTC; same 622 tracks and randomized partitions",
    )
    axes[0, 0].tick_params(axis="x", rotation=25)
    right.set_ylabel("Held-out RMS (Hz)")
    handles, names = axes[0, 0].get_legend_handles_labels()
    other_handles, other_names = right.get_legend_handles_labels()
    axes[0, 0].legend(handles + other_handles, names + other_names, fontsize=8)
    axes[0, 0].grid(axis="y", alpha=0.25)

    markers = {"norad": "o", "session": "s"}
    for number, mode in enumerate(["repeated_satellites", "all_satellites_flexibility_control"]):
        for grouping in ["norad", "session"]:
            selected = [
                row for row in stability if row["mode"] == mode and row["grouping"] == grouping
            ]
            axes[0, 1].scatter(
                np.full(len(selected), number) + (-0.08 if grouping == "norad" else 0.08),
                [row["horizontal_error_m"] / 1000 for row in selected],
                marker=markers[grouping],
                s=45,
                label=grouping.upper() if number == 0 else None,
            )
    axes[0, 1].axhline(1, color="black", ls="--", lw=1, label="1 km")
    axes[0, 1].set(
        xticks=[0, 1],
        xticklabels=["Repeated IDs", "All IDs exploratory"],
        ylabel="Horizontal error (km)",
        title="Four leave-one-fold-out refits per grouping",
    )
    axes[0, 1].grid(axis="y", alpha=0.25)
    axes[0, 1].legend(fontsize=8)

    for number, mode in enumerate(["repeated_satellites", "all_satellites_flexibility_control"]):
        selected = sorted(
            [row for row in sensitivity if row["mode"] == mode],
            key=lambda row: row["prior_sigma_factor"],
        )
        main = repeated if number == 0 else flexible
        factors = [row["prior_sigma_factor"] for row in selected] + [1.0]
        values = [row["horizontal_error_m"] / 1000 for row in selected] + [
            main["horizontal_error_m"] / 1000
        ]
        order = np.argsort(factors)
        axes[1, 0].plot(
            np.asarray(factors)[order],
            np.asarray(values)[order],
            "o-",
            label="Repeated IDs" if number == 0 else "All IDs exploratory",
        )
    axes[1, 0].set(
        xscale="log",
        xticks=[0.5, 1, 2],
        xticklabels=["0.5×", "1×", "2×"],
        xlabel="Empirical phase-rate prior width",
        ylabel="Horizontal error (km)",
        title="Predeclared prior-width sensitivity",
    )
    axes[1, 0].grid(alpha=0.25)
    axes[1, 0].legend(fontsize=8)

    for row, label in [(repeated, "Repeated IDs"), (flexible, "All IDs exploratory")]:
        values = np.asarray(list(row["rate_corrections_s_h"].values()))
        axes[1, 1].hist(values, bins=30, histtype="step", lw=1.7, label=label)
    axes[1, 1].axvline(-0.25, color="black", ls=":", lw=1)
    axes[1, 1].axvline(0.25, color="black", ls=":", lw=1, label="Bounds")
    axes[1, 1].set(
        xlabel="Fitted phase-rate correction (s/h)",
        ylabel="Satellites",
        title="Regularized training-only corrections",
    )
    axes[1, 1].grid(axis="y", alpha=0.25)
    axes[1, 1].legend(fontsize=8)
    fig.suptitle(
        "Strictly causal orbital phase uncertainty\n"
        "Known coordinate appears only in this post-inference evaluation"
    )
    fig.savefig(args.output / "uncertainty.png", dpi=170)
    plt.close(fig)
    print(json.dumps({key: value for key, value in summary.items() if "fraction" in key}, indent=2))


if __name__ == "__main__":
    main()
