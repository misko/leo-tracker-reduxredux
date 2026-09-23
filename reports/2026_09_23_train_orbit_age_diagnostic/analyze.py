#!/usr/bin/env python3
"""Describe sealed paired common residuals against actual TLE element age."""

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
PAIRS = ROOT / "reports/2026_09_23_train_receiver_orbit_diagnostic/results/inference.json"
EPOCHS = Path("/tmp/leo-train-orbit-epochs.json")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def correlation(x, y):
    return {
        "pearson_r": float(pearsonr(x, y).statistic),
        "spearman_rho": float(spearmanr(x, y).statistic),
    }


def demean(values, labels):
    result = values.copy()
    for label in sorted(set(labels)):
        mask = labels == label
        result[mask] -= np.mean(result[mask])
    return result


def main():
    paired = json.loads(PAIRS.read_text())
    recovered = json.loads(EPOCHS.read_text())
    epochs = {(row["session_id"], row["candidate_id"]): row for row in recovered["rows"]}
    rows = []
    for pair in paired["pairs"]:
        key = (pair["session_id"], pair["candidate_id"])
        if key not in epochs:
            raise ValueError(f"missing exact epoch join: {key}")
        epoch = epochs[key]
        reference_ns = epoch["snapshot_collected_utc_ns"] + round(
            pair["snapshot_collection_age_s"] * 1e9
        )
        rows.append(
            {
                **pair,
                "element_epoch_utc_ns": epoch["element_epoch_utc_ns"],
                "element_age_s": (reference_ns - epoch["element_epoch_utc_ns"]) / 1e9,
            }
        )
    age_days = np.asarray([row["element_age_s"] / 86400 for row in rows])
    slope = np.asarray([row["common_slope_hz_s"] for row in rows])
    quadratic = np.asarray([row["common_quadratic_hz_s2"] for row in rows])
    labels = np.asarray(
        [f"{row['train_group']}|{row['lane']}|{row['look_quadrant']}" for row in rows]
    )
    adjusted_age = demean(age_days, labels)
    adjusted_slope = demean(slope, labels)
    adjusted_quadratic = demean(quadratic, labels)
    edges = np.quantile(age_days, [0, 0.25, 0.5, 0.75, 1])
    bins = []
    for index in range(4):
        mask = (age_days >= edges[index]) & (
            age_days <= edges[index + 1] if index == 3 else age_days < edges[index + 1]
        )
        bins.append(
            {
                "minimum_age_days": float(edges[index]),
                "maximum_age_days": float(edges[index + 1]),
                "row_count": int(np.sum(mask)),
                "group_count": len({rows[i]["group"] for i in np.flatnonzero(mask)}),
                "mean_common_slope_hz_s": float(np.mean(slope[mask])),
                "mean_common_quadratic_hz_s2": float(np.mean(quadratic[mask])),
            }
        )
    result = {
        "schema": "train-orbit-age-diagnostic/v1",
        "truth_used": False,
        "validation_or_test_used": False,
        "position_refit_performed": False,
        "pair_count": len(rows),
        "session_count": len({row["session_id"] for row in rows}),
        "session_candidate_count": len(epochs),
        "element_age_days": {
            "minimum": float(np.min(age_days)),
            "median": float(np.median(age_days)),
            "maximum": float(np.max(age_days)),
        },
        "marginal": {
            "common_slope": correlation(age_days, slope),
            "common_quadratic": correlation(age_days, quadratic),
        },
        "within_train_lane_look": {
            "common_slope": correlation(adjusted_age, adjusted_slope),
            "common_quadratic": correlation(adjusted_age, adjusted_quadratic),
        },
        "age_bins": bins,
        "bindings": {
            "protocol": digest(HERE / "PROTOCOL.md"),
            "analyzer": digest(Path(__file__)),
            "helper": digest(HERE / "recover_epochs.py"),
            "paired_inference": digest(PAIRS),
            "epoch_recovery": digest(EPOCHS),
            "snapshot_records": sorted(
                {
                    (row["snapshot_digest"], row["snapshot_collected_utc_ns"])
                    for row in recovered["rows"]
                }
            ),
        },
    }
    result_path = HERE / "results.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (HERE / "results.sha256").write_text(
        hashlib.sha256(result_path.read_bytes()).hexdigest() + "\n"
    )
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    axes[0].scatter(age_days, slope, s=10, alpha=0.45)
    axes[0].set(xlabel="actual element age (days)", ylabel="common slope (Hz/s)")
    axes[1].scatter(adjusted_age, adjusted_slope, s=10, alpha=0.45)
    axes[1].set(xlabel="age within TRAIN/lane/look (days)", ylabel="slope within stratum (Hz/s)")
    for axis in axes:
        axis.grid(alpha=0.2)
    figure.savefig(HERE / "orbit_age.png", dpi=180)


if __name__ == "__main__":
    main()
