#!/usr/bin/env python3
"""Plot the frozen left-to-right prediction for a cohort handoff candidate."""

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_pnt_cohort import make_arc
from evaluate_scan_pnt_longitudinal import BASE, polynomial_predict, states

from leo.analysis.research.scan_pnt_experiment import (
    doppler_from_ecef,
    remove_offsets,
    split_segments,
)
from leo.sky.propagation import parse_element_sets


def main():
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output
    data = json.loads((root / "longitudinal.json").read_text())
    chosen = next(row for row in data["handoffs"] if row["supported"])
    sid = chosen["session_id"]
    doc = json.loads((root / "evidence" / f"{sid}.json").read_text())
    result = json.loads((root / "results" / f"{sid}.json").read_text())
    left = next(ep for ep in result["episodes"] if ep["episode_id"] == chosen["left"])
    right = next(ep for ep in result["episodes"] if ep["episode_id"] == chosen["right"])
    a, b = make_arc(doc, left["members"]), make_arc(doc, right["members"])
    reference = doc["inventory"]["reference_utc_ns"]
    cat = parse_element_sets((root / "evidence" / doc["inventory"]["tle_file"]).read_text())
    sat = cat.satellites[cat.satellite_numbers.index(chosen["norad_from_left_training"])]
    tau = chosen["tau_from_left_s"]
    left_training, _ = split_segments(a)
    right_calibration, right_evaluation = split_segments(b, 0.4)
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), layout="constrained", sharex=True)
    for arc, training, label, color in (
        (a, left_training, left["label"], "#1976a3"),
        (b, right_calibration, right["label"], "#c65b35"),
    ):
        p, v = states(sat, reference, arc.time_s, tau)
        model = doppler_from_ecef(p, v, BASE)
        residual = remove_offsets(arc.frequency_hz - model, arc.segment, training)
        axes[0].scatter(arc.time_s, (model + residual) / 1000, s=12, color=color, label=label)
        if arc is b:
            axes[1].scatter(
                arc.time_s[right_evaluation],
                residual[right_evaluation],
                s=18,
                color=color,
                label="Frozen TLE: right held-out residual",
            )
    t = np.arange(a.time_s.min(), b.time_s.max(), 0.1)
    p, v = states(sat, reference, t, tau)
    axes[0].plot(
        t,
        doppler_from_ecef(p, v, BASE) / 1000,
        color="black",
        lw=1.5,
        label=f"NORAD {chosen['norad_from_left_training']}, τ={tau:+.2f} s",
    )
    predicted = polynomial_predict(a, b, left_training, 0, 3)
    residual = remove_offsets(b.frequency_hz - predicted, b.segment, right_calibration)
    axes[1].scatter(
        b.time_s[right_evaluation],
        residual[right_evaluation],
        marker="x",
        s=18,
        color="#8655a3",
        label="Left-only cubic: right held-out residual",
    )
    for ax in axes:
        ax.axvline(b.time_s.min(), color="#777777", ls="--", lw=1)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9)
    axes[0].set_ylabel("Normalized CFO after learned offsets (kHz)")
    axes[1].set_ylabel("Residual (Hz)")
    axes[1].axhline(0, color="black", lw=0.8)
    axes[1].set_xlabel("Device time since scan start (s)")
    fig.suptitle(
        f"{sid}: CH4 → CH1 candidate, STARLINK-36479\n"
        "Left training selects orbit and τ; early right samples learn only frequency offsets"
    )
    fig.savefig(root / "13-predictive-channel-handoff.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
