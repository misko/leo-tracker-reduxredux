#!/usr/bin/env python3
"""Plot signed nearest-candidate residuals for frozen nominees in every lane."""

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

DISPLAY_PRIOR = 1e-6
RECEIVERS = ("rx0", "rx1")


def receiver_row(nominee, receiver):
    return next(row for row in nominee["receivers"] if row["receiver"] == receiver)


def lane_label(lane):
    identity = lane["lane"]
    session = lane["session_id"].removeprefix("scan-fw-")[:6]
    channel = identity.get("channel", identity.get("channel_index", "?"))
    edge = identity.get("edge", identity.get("edge_name", "?"))
    return f"{session}  ch{channel} {edge}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if result.get("schema") != "rx-residual-trajectories/v1":
        raise ValueError("unsupported residual-trajectory schema")
    if result.get("status") != "complete" or len(result.get("lanes", [])) != 12:
        raise ValueError("results are not complete twelve-lane evidence")
    outputs = [
        args.output_prefix.parent / f"{args.output_prefix.name}-{receiver}{suffix}"
        for receiver in RECEIVERS
        for suffix in (".png", ".svg")
    ]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")

    lanes = sorted(
        result["lanes"],
        key=lambda row: (
            row["session_id"],
            json.dumps(row["lane"], sort_keys=True, separators=(",", ":")),
        ),
    )
    for receiver in RECEIVERS:
        figure, axes = plt.subplots(3, 4, figsize=(16, 10), constrained_layout=True, sharey=True)
        for axis, lane in zip(axes.flat, lanes, strict=True):
            displayed = [
                nominee
                for nominee in lane["nominees"]
                if nominee["prior_probability"] >= DISPLAY_PRIOR
            ]
            maximum = max(nominee["prior_probability"] for nominee in displayed)
            observed_points = 0
            possible_points = 0
            boundary = None
            for nominee_index, nominee in enumerate(displayed):
                weight = nominee["prior_probability"]
                emphasis = math.sqrt(weight / maximum)
                alpha = 0.15 + 0.75 * emphasis
                size = 5 + 23 * emphasis
                row = receiver_row(nominee, receiver)
                boundary = boundary or row["role_boundary"]
                color = plt.get_cmap("tab20")(nominee_index % 20)
                for role, marker in (("reception", "o"), ("held_frequency", "^")):
                    windows = [window for window in row["windows"] if window["role"] == role]
                    possible_points += len(windows)
                    selected = [window for window in windows if window["nearest"] is not None]
                    observed_points += len(selected)
                    axis.scatter(
                        [window["elapsed_s"] for window in selected],
                        [
                            window["nearest"]["signed_residual_hz"]
                            / lane["alias_period_hz"]
                            for window in selected
                        ],
                        marker=marker,
                        color=color,
                        alpha=alpha,
                        s=size,
                        linewidths=0,
                    )
            if boundary is not None:
                boundary_s = (
                    boundary["first_held_utc_ns"] - boundary["last_reception_utc_ns"]
                ) / 2e9
                last_reception = next(
                    window["elapsed_s"]
                    for window in receiver_row(displayed[0], receiver)["windows"]
                    if window["source_window_id"]
                    == boundary["last_reception_source_window_id"]
                )
                axis.axvline(last_reception + boundary_s, color="#333333", linewidth=0.8)
            summary = lane["nomination_summary"]
            axis.set_title(
                f"{lane_label(lane)}\n"
                f"shown {len(displayed)}/{summary['nominees']}; "
                f"below threshold {summary['finite_below_1e_6_count']}; "
                f"observed {observed_points}/{possible_points}",
                fontsize=9,
            )
            axis.axhline(0, color="#777777", linewidth=0.6)
            axis.set_ylim(-0.51, 0.51)
            axis.grid(axis="y", alpha=0.15)
        for axis in axes[-1]:
            axis.set_xlabel("seconds since lane reception start")
        for axis in axes[:, 0]:
            axis.set_ylabel("signed residual / alias period")
        handles = [
            Line2D([], [], marker="o", linestyle="none", color="#444444", label="reception"),
            Line2D(
                [], [], marker="^", linestyle="none", color="#444444", label="held frequency"
            ),
            Line2D([], [], linestyle="-", color="#333333", label="role boundary"),
        ]
        figure.legend(handles=handles, loc="outside upper right", frameon=False)
        figure.suptitle(
            f"{receiver.upper()} signed nearest-candidate residuals: all nominees with frozen "
            f"prior ≥ {DISPLAY_PRIOR:g}\n"
            "Scatter only: nearest-candidate identities may switch; color distinguishes nominees "
            "within a lane and opacity/size follows prior mass"
        )
        for suffix in (".png", ".svg"):
            output = args.output_prefix.parent / f"{args.output_prefix.name}-{receiver}{suffix}"
            figure.savefig(output, dpi=180 if suffix == ".png" else None)
        plt.close(figure)


if __name__ == "__main__":
    main()
