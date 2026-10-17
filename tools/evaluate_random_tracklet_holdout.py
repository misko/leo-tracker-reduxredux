"""Rerun frozen tracklet methods with balanced random-point cross-validation."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
from pathlib import Path

import numpy as np
from compare_tracklet_methods import METHODS
from evaluate_polynomial_tracklets import DEFAULT_INPUT, REPO, digest, load_observations
from validate_polynomial_tracklet_predictions import cross_validate, make_folds

from leo.analysis.polynomial_tracklets import TrackConfig

INTERVAL_ROOT = REPO / "reports/2026_10_17_dsx01_four_methods"
OUTPUT = REPO / "reports/2026_10_17_dsx01_random_holdout"
LABELS = {
    "baseline": "RANSAC baseline",
    "em": "Wrapped EM",
    "graph": "Graph DP",
    "hough": "Hough voting",
    "mht": "MHT",
}


def evaluate(method, output, seed):
    module = importlib.import_module(METHODS[method])
    previous = json.loads((INTERVAL_ROOT / method / "comparison.json").read_text())
    rows, provenance = load_observations(DEFAULT_INPUT)
    assert previous["provenance"]["input_sha256"] == provenance["input_sha256"]
    # Freeze algorithm and common numerical code; only the holdout protocol changes.
    for path, expected in previous["provenance"]["source_hashes"].items():
        if path.startswith("src/leo/analysis/") and digest(REPO / path) != expected:
            raise ValueError(f"Algorithm differs from interval comparison: {path}")
    cfg = TrackConfig(**previous["config"])
    source_paths = [
        Path(module.__file__),
        REPO / "src/leo/analysis/polynomial_tracklets.py",
        REPO / "src/leo/analysis/tracklet_fitting.py",
        Path(__file__),
        REPO / "tools/validate_polynomial_tracklet_predictions.py",
    ]
    hashes = {str(p.relative_to(REPO)): digest(p) for p in source_paths}
    directory = output / method
    directory.mkdir(parents=True, exist_ok=True)
    fold_assignment = make_folds(rows, split="random_points", seed=seed)
    with (directory / "folds.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["observation_id", "receiver", "channel", "time_s", "fold"]
        )
        writer.writeheader()
        writer.writerows(
            {
                **{k: row[k] for k in ("observation_id", "receiver", "channel", "time_s")},
                "fold": int(fold_assignment[i]),
            }
            for i, row in enumerate(rows)
        )
    result = cross_validate(rows, cfg, module.fit_lane, split="random_points", seed=seed)
    assert result["observations"] == len(rows) == 4797
    assert sum(f["excluded_points"] for f in result["folds"]) == len(rows)
    assert all(digest(REPO / path) == value for path, value in hashes.items())
    document = {
        "method": method,
        "label": LABELS[method],
        "provenance": {
            **provenance,
            "source_hashes": hashes,
            "fold_csv_sha256": digest(directory / "folds.csv"),
            "previous_receipt_sha256": digest(INTERVAL_ROOT / method / "comparison.json"),
        },
        "protocol": "Four balanced folds of randomly selected individual observations, stratified "
        "within each receiver/channel lane. Seeded independently of measured CFO and "
        "fitted memberships. Discover tracks from training points only; score every "
        "original point once. Same algorithms, coefficients, final 450 Hz residual gate, "
        "and predictive density as the prior interval test. No extrapolation outside "
        "training support. No full-data track or alias assignments reused.",
        "random_point_prediction": result,
        "previous_interval_prediction": previous["heldout_prediction"],
        "unchanged_full_data_fit": {
            k: previous["real_data"][k] for k in ("track_count", "assigned", "assigned_fraction")
        },
        "limits": "Single-seed development comparison on inspected S01. Prediction means proximity "
        "to at least one training curve, not validated track or satellite identity. "
        "Random-point holdout retains nearby training observations.",
    }
    (directory / "results.json").write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "method": method,
                "random_predicted": result["points_within_3sigma_of_training_prediction"],
                "random_fraction": result["predictive_coverage_fraction"],
                "interval_fraction": previous["heldout_prediction"]["predictive_coverage_fraction"],
                "mean_log_gain": result["mean_log_density_gain_over_uniform_nats"],
            }
        ),
        flush=True,
    )


def summarize(output):
    reports = {m: json.loads((output / m / "results.json").read_text()) for m in METHODS}
    manifests = {
        r["random_point_prediction"]["split"]["assignment_sha256"] for r in reports.values()
    }
    assert len(manifests) == 1, "Every method must use identical withheld points"
    csv_hashes = {r["provenance"]["fold_csv_sha256"] for r in reports.values()}
    assert len(csv_hashes) == 1
    (output / "folds.csv").write_bytes((output / "baseline/folds.csv").read_bytes())
    summary = []
    for method, report in reports.items():
        random, blocked = report["random_point_prediction"], report["previous_interval_prediction"]
        summary.append(
            {
                "method": method,
                "label": LABELS[method],
                "observations": random["observations"],
                "random_predicted_points": random["points_within_3sigma_of_training_prediction"],
                "random_prediction_fraction": random["predictive_coverage_fraction"],
                "interval_predicted_points": blocked["points_within_3sigma_of_training_prediction"],
                "interval_prediction_fraction": blocked["predictive_coverage_fraction"],
                "random_mean_log_density_gain_nats": random[
                    "mean_log_density_gain_over_uniform_nats"
                ],
                "random_runtime_s": random["runtime_s"],
            }
        )
    with (output / "comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    (output / "summary.json").write_text(
        json.dumps(
            {
                "protocol": reports["baseline"]["protocol"],
                "split": reports["baseline"]["random_point_prediction"]["split"],
                "methods": summary,
                "limits": reports["baseline"]["limits"],
                "validation": "All five methods use identical fold CSVs and unchanged algorithms; "
                "all 4,797 observations are predicted once; historical results are unchanged.",
            },
            indent=2,
        )
        + "\n"
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5.5))
    y = np.arange(len(summary))
    for offset, key, label, color in [
        (-0.18, "interval_prediction_fraction", "5-second interval holdout", "#8ba4b4"),
        (0.18, "random_prediction_fraction", "Random individual-point holdout", "#187c8b"),
    ]:
        values = np.array([r[key] for r in summary]) * 100
        ax.barh(y + offset, values, height=0.33, color=color, label=label)
        for i, value in enumerate(values):
            ax.text(value + 0.6, i + offset, f"{value:.1f}%", va="center", fontsize=10)
    ax.set(
        yticks=y,
        yticklabels=[r["label"] for r in summary],
        xlim=(0, 100),
        xlabel="Excluded points within 450 Hz of a training curve (%)",
        title="DSX01 S01 · Random-point versus interval holdout",
    )
    ax.invert_yaxis()
    ax.set_ylim(len(summary) + 0.25, -0.65)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right")
    fig.text(
        0.5,
        0.02,
        "Four folds; all 4,797 observations scored once. Random seed 1701; "
        "identical splits across methods.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for extension in ("png", "pdf"):
        fig.savefig(output / f"comparison.{extension}", dpi=170)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS)
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.summarize:
        summarize(args.output_dir)
    elif args.method:
        evaluate(args.method, args.output_dir, args.seed)
    else:
        parser.error("Choose --method or --summarize")


if __name__ == "__main__":
    main()
