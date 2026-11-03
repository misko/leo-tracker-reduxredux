"""Conditional drift sensitivity; no changes to the benchmark fits."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import models
import numpy as np
from bundle import Data
from fast_tracks import fit_track_shared
from investigate_sample import SESSION, save
from plot_independent_offsets import align_alias
from selection import ROOT


def line_values(line, times):
    return line[0] + line[1] * (np.asarray(times) - 150)


def main():
    directory = ROOT / "scans" / SESSION
    output = ROOT / f"investigation-{SESSION}"
    fits = json.loads((directory / "fits.json").read_text())["models"]
    parameters = np.asarray(fits["track_linear"]["parameters"])
    data = Data(directory)
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    prediction, visible = context.cache.get(parameters[:2])
    blocks = models._track_blocks(context, prediction, visible)
    _, baseline, lines = fit_track_shared(blocks, initial, 10.0)
    for receiver in (0, 1):
        np.testing.assert_allclose(
            lines[receiver], parameters[2 + 2 * receiver : 4 + 2 * receiver], atol=1e-7
        )
    experiments = []
    for block in blocks:
        retained = [row for row in blocks if row["track_index"] != block["track_index"]]
        _, selected, fitted_lines = fit_track_shared(retained, initial, 10.0)
        experiments.append(
            {
                "omitted_track": block["track_index"],
                "rx": block["receiver"],
                "lines": {str(receiver): line.tolist() for receiver, line in fitted_lines.items()},
                "accepted_tracks": sum(row["accepted"] for row in selected),
            }
        )
    independent_points = json.loads((output / "diagnostics.json").read_text())["diagnostics"][
        "track_independent"
    ]["track_points"]
    outliers = [row["track_index"] for row in independent_points if row["offset_hz"] > 115000]
    _, _, without_outliers = fit_track_shared(
        [row for row in blocks if row["track_index"] not in outliers], initial, 10.0
    )
    figure, axes = plt.subplots(
        2, 2, figsize=(16, 10), sharex=True, sharey=True, constrained_layout=True
    )
    times = np.linspace(0, 300, 301)
    summary = {}
    for receiver in (0, 1):
        line = lines[receiver]
        label = f"Shared fit: {line[0] / 1000:.3f} kHz at 150 s; slope {line[1]:+.2f} Hz/s"
        left, right = axes[receiver]
        left.set_title(f"RX{receiver}: previous independent offsets (1.37 km solution)")
        for row in independent_points:
            if row["rx"] == receiver:
                left.errorbar(
                    row["center_s"],
                    row["offset_hz"] / 1000,
                    xerr=row["duration_s"] / 2,
                    fmt="o",
                    color="#0072b2",
                    alpha=0.65,
                    ms=4,
                    lw=0.8,
                )
        left.plot(
            times,
            line_values(line, times) / 1000,
            "--",
            color="black",
            label="Shared-fit line: different position, comparison only",
        )
        for accepted, color, marker in ((True, "#0072b2", "o"), (False, "#d55e00", "x")):
            local = [
                row
                for row in baseline
                if row["receiver"] == receiver and row["accepted"] == accepted
            ]
            for index, row in enumerate(local):
                center = (np.min(row["times"]) + np.max(row["times"])) / 2 + 150
                offset = models._robust_column_locations(row["residual"][:, [row["satellite"]]])[0]
                offset = align_alias(offset, line_values(line, center))
                right.errorbar(
                    center,
                    offset / 1000,
                    xerr=np.ptp(row["times"]) / 2,
                    fmt=marker,
                    color=color,
                    alpha=0.65,
                    ms=4,
                    lw=0.8,
                    label=("Accepted tracks" if accepted else "Rejected tracks")
                    if index == 0
                    else None,
                )
        local_experiments = [row for row in experiments if row["rx"] == receiver]
        trial_lines = np.array([row["lines"][str(receiver)] for row in local_experiments])
        curves = trial_lines[:, :1] + trial_lines[:, 1:] * (times[None, :] - 150)
        right.fill_between(
            times,
            np.min(curves, axis=0) / 1000,
            np.max(curves, axis=0) / 1000,
            color="#cc79a7",
            alpha=0.25,
            label="Leave-one-track-out range (not confidence interval)",
        )
        right.plot(times, line_values(line, times) / 1000, color="black", lw=2, label=label)
        right.set_title(f"RX{receiver}: actual shared-linear fit (5.15 km solution)")
        changes = np.max(np.abs(curves - line_values(line, times)), axis=1)
        worst = int(np.argmax(changes))
        summary[str(receiver)] = {
            "actual_intercept_hz_at_150s": float(line[0]),
            "actual_slope_hz_s": float(line[1]),
            "leave_one_out_slope_range_hz_s": [
                float(min(trial_lines[:, 1])),
                float(max(trial_lines[:, 1])),
            ],
            "maximum_curve_change_hz": float(changes[worst]),
            "most_influential_omitted_track": local_experiments[worst]["omitted_track"],
            "without_high_offset_outliers": without_outliers[receiver].tolist(),
            "accepted_tracks": sum(
                row["accepted"] for row in baseline if row["receiver"] == receiver
            ),
            "total_tracks": sum(row["receiver"] == receiver for row in baseline),
        }
        for axis in (left, right):
            axis.set(xlim=(0, 300), ylabel="Dealiased constant offset (kHz)")
            axis.grid(alpha=0.2)
            axis.legend(fontsize=7, loc="upper right")
    for axis in axes[-1]:
        axis.set_xlabel("Scan time (s)")
    figure.suptitle(
        SESSION + " — actual LNB drift lines and outlier sensitivity\n"
        "Right: position held fixed; satellite choices and RX lines refitted after "
        "each deletion. Bars show track duration.",
        fontsize=12,
    )
    save(figure, output, "06-lnb-drift-sensitivity")
    receipt = {
        "scope": "Conditional nuisance refits at fixed shared-fit position; not joint "
        "position sensitivity or confidence intervals",
        "receivers": summary,
        "high_offset_outlier_tracks": outliers,
        "leave_one_track_out": experiments,
    }
    (output / "drift-sensitivity.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
