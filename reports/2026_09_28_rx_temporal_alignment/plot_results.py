#!/usr/bin/env python3
"""Plot equal-record temporal alignment summaries with explicit bin support."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROLES = ("reception", "held_frequency")
ROLE_LABELS = {"reception": "reception", "held_frequency": "held frequency"}
BINS = ("0-30", "30-60", "60-90", "90-120", "120-180", "180-infinity")


def series(result, role, metric):
    values = []
    support = []
    for label in BINS:
        row = result["aggregate_equal_record"][f"{role}:{label}"]
        value = row["equal_record_mean"][metric]
        values.append(np.nan if value is None else value)
        support.append((row["recordings_with_windows"], row["windows"]))
    return np.asarray(values), support


def supported_x(result, role):
    return np.asarray(
        [
            index
            for index, label in enumerate(BINS)
            if result["aggregate_equal_record"][f"{role}:{label}"]["windows"] > 0
        ]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if result.get("schema") != "rx-temporal-alignment/v1" or result.get("status") != "complete":
        raise ValueError("results are not complete temporal-alignment evidence")
    outputs = [args.output_prefix.with_suffix(suffix) for suffix in (".png", ".svg")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")

    figure, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    colors = {500: "#2864a8", 1500: "#b44c27"}
    styles = {"rx0": "-", "rx1": "--"}
    for axis, role in zip(axes[0, :2], ROLES, strict=True):
        x = supported_x(result, role)
        for threshold in (500, 1500):
            for receiver in ("rx0", "rx1"):
                metric = f"prior_probability_nearest_le_{threshold}hz_{receiver}"
                values, _ = series(result, role, metric)
                axis.plot(
                    x,
                    values[x],
                    marker="o",
                    color=colors[threshold],
                    linestyle=styles[receiver],
                    label=f"{receiver.upper()} ≤{threshold} Hz",
                )
        axis.set_title(f"Alignment: {ROLE_LABELS[role]}")
        axis.set_ylim(-0.02, 1.02)
        axis.set_ylabel("prior mass aligned")
        axis.grid(axis="y", alpha=0.2)
    axes[0, 0].legend(frameon=False, fontsize=8, ncol=2)

    support_axis = axes[0, 2]
    for role, marker in zip(ROLES, ("o", "s"), strict=True):
        windows = [
            result["aggregate_equal_record"][f"{role}:{label}"]["windows"] for label in BINS
        ]
        x = supported_x(result, role)
        support_axis.scatter(x, np.asarray(windows)[x], marker=marker, label=ROLE_LABELS[role])
        for index in x:
            row = result["aggregate_equal_record"][f"{role}:{BINS[index]}"]
            support_axis.annotate(
                f"{row['recordings_with_windows']} rec",
                (index, windows[index]),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                fontsize=7,
            )
    support_axis.set_title("Observed support (empty bins omitted)")
    support_axis.set_ylabel("windows")
    support_axis.legend(frameon=False, fontsize=8)
    support_axis.grid(axis="y", alpha=0.2)

    bottom_specs = (
        ("Candidate count", ("candidate_count_rx0", "candidate_count_rx1"), ("RX0", "RX1")),
        (
            "Relative score",
            ("D_relative_log_score", "T_relative_log_score"),
            ("D", "T"),
        ),
        (
            "Posterior presence state (not confidence)",
            ("D_presence_probability", "T_presence_probability"),
            ("D", "T"),
        ),
    )
    for axis, (title, metrics, labels) in zip(axes[1], bottom_specs, strict=True):
        for role, marker in zip(ROLES, ("o", "s"), strict=True):
            x = supported_x(result, role)
            for metric, label, linestyle in zip(metrics, labels, ("-", "--"), strict=True):
                values, _ = series(result, role, metric)
                axis.plot(
                    x,
                    values[x],
                    marker=marker,
                    linestyle=linestyle,
                    label=f"{ROLE_LABELS[role]} {label}",
                )
        axis.axhline(0, color="#555555", linewidth=0.8)
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.2)
        axis.legend(frameon=False, fontsize=7)
    axes[1, 2].set_ylim(-0.02, 1.02)

    for axis in axes.flat:
        axis.set_xticks(np.arange(len(BINS)), BINS, rotation=35, ha="right")
        axis.set_xlabel("seconds since each lane's first reception window")
    figure.suptitle(
        "Temporal candidate alignment and frozen-model diagnostics\n"
        "Role and elapsed time are nearly confounded; elapsed is not forecast age"
    )
    for path in outputs:
        figure.savefig(path, dpi=180 if path.suffix == ".png" else None)
    plt.close(figure)


if __name__ == "__main__":
    main()
