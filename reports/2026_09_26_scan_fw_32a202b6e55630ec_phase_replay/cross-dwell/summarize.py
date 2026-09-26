#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def circ(x):
    return float(abs(np.mean(np.exp(1j * np.radians(x)))))


def main(src, out):
    rows = [json.loads(x) for x in src.read_text().splitlines()]
    ok = [x for x in rows if x["status"] == "complete"]
    dev = [x for x in ok if x["split"] == "development"]
    ev = [x for x in ok if x["split"] == "evaluation"]
    # Development-only zero-centered pairing calibration; no satellite identity enters.
    bias = float(
        np.degrees(
            np.angle(
                np.mean(
                    np.exp(1j * np.radians([x["causal_left_boundary_residual_deg"] for x in dev]))
                )
            )
        )
    )
    result = {
        "ledger": len(rows),
        "complete": len(ok),
        "rejected": len(rows) - len(ok),
        "rejection_reasons": {},
        "development": len(dev),
        "evaluation": len(ev),
        "development_bias_deg": bias,
    }
    for row in rows:
        if row["status"] != "complete":
            result["rejection_reasons"][row["reason"]] = (
                result["rejection_reasons"].get(row["reason"], 0) + 1
            )
    for name, part in [("development", dev), ("evaluation", ev)]:
        vals = np.array([x["causal_left_boundary_residual_deg"] for x in part])
        calibrated = (vals - bias + 180) % 360 - 180
        result[name + "_causal_r"] = circ(vals)
        result[name + "_calibrated_r"] = circ(calibrated)
        result[name + "_calibrated_median_abs_deg"] = float(np.median(abs(calibrated)))
        result[name + "_joint_r"] = circ([x["joint_boundary_residual_deg"] for x in part])
        result[name + "_strict_joint_r"] = circ(
            [x["strict_joint_boundary_residual_deg"] for x in part]
        )
        result[name + "_groups"] = len({x["overlapping_edge_group"] for x in part})
        result[name + "_wrong_alias_r"] = circ(
            [x["wrong_alias_boundary_residual_deg"] for x in part]
        )
        result[name + "_wrong_receiver_time_r"] = circ(
            [x["wrong_receiver_time_boundary_residual_deg"] for x in part]
        )
        result[name + "_median_endpoint_coherence"] = float(
            np.median([x["minimum_boundary_endpoint_coherence"] for x in part])
        )
    result["evaluation_by_channel"] = {
        str(c): {
            "count": len(p),
            "causal_r": circ([x["causal_left_boundary_residual_deg"] for x in p]),
            "median_abs_deg": float(
                np.median(
                    abs(
                        (np.array([x["causal_left_boundary_residual_deg"] for x in p]) - bias + 180)
                        % 360
                        - 180
                    )
                )
            ),
        }
        for c in sorted({x["channel"] for x in ev})
        if (p := [x for x in ev if x["channel"] == c])
    }
    result["train_selected_alias_counts"] = {
        str(a): sum(x["train_selected_symbol_alias"] == a for x in ok) for a in (-1, 0, 1)
    }
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for split, marker in [("development", "o"), ("evaluation", "x")]:
        p = [x for x in ok if x["split"] == split]
        ax.scatter(
            [x["minimum_boundary_endpoint_coherence"] for x in p],
            [x["causal_left_boundary_residual_deg"] for x in p],
            s=24,
            alpha=0.7,
            marker=marker,
            label=split,
        )
    ax.axhline(0, color="black", lw=0.8)
    ax.set(xlabel="minimum endpoint coherence", ylabel="strict causal boundary residual (degrees)")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out.with_suffix(".png"), dpi=160)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    main(a.src, a.out)
