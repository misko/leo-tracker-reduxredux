"""Render paired, support-disjoint bandwidth results from saved observations."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main(input_path, prefix):
    rows = [json.loads(line) for line in input_path.read_text().splitlines()]
    complete = [row for row in rows if row["status"] == "completed"]
    held = [row for row in complete if row["split"] == "evaluation"]
    summary = {
        "schema": "scan-guarded-spectral-summary/v5",
        "source_file": str(input_path),
        "eligible": len(rows),
        "completed": len(complete),
        "evaluation_completed": len(held),
        "native_window_samples": 32768,
        "native_fir_half_support_samples": 128,
        "split_policy": "same raw-disjoint random and forward block indices at both rates",
        "mask_policy": "physical overlap and magnitude mask fitted on training FFTs only",
        "runtime_seconds": sum(row["runtime_seconds"] for row in rows),
        "medians": {},
        "supersedes": (
            "spectral results-v1/v2/v3 holdout claims; "
            "v3 had overlapping transform/FIR support"
        ),
    }
    keys = (
        "train_r",
        "held_r",
        "held_zero_intercept_rms_deg",
        "held_median_coherence",
        "parseval_rms_rad",
    )
    for rate in ("native", "derived_2p5"):
        summary["medians"][rate] = {}
        for split in ("random", "forward"):
            metrics = {
                key: float(np.median([row[rate][split][key] for row in held])) for key in keys
            }
            metrics["fft_held_r"] = {
                key: float(np.median([row[rate][split]["fft_held_r"][key] for row in held]))
                for key in held[0][rate][split]["fft_held_r"]
            }
            summary["medians"][rate][split] = metrics
    (HERE / f"{prefix}.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    labels = ["10 MS/s\nrandom", "2.5 MS/s\nrandom", "10 MS/s\nforward", "2.5 MS/s\nforward"]
    order = [(rate, split) for split in ("random", "forward") for rate in ("native", "derived_2p5")]
    x = np.arange(4)
    for delta, key, label, color in (
        (-0.18, "train_r", "Training", "#97b5c6"),
        (0.18, "held_r", "Held", "#245775"),
    ):
        axes[0].bar(
            x + delta,
            [summary["medians"][rate][split][key] for rate, split in order],
            0.36,
            label=label,
            color=color,
        )
    axes[0].set(
        xticks=x,
        xticklabels=labels,
        ylim=(0, 1),
        ylabel="Median ordinary 2π concentration R",
        title="Prediction on disjoint raw support",
    )
    axes[0].legend(frameon=False)
    for split, marker in (("random", "o"), ("forward", "s")):
        metrics = summary["medians"]["native"][split]["fft_held_r"]
        widths = sorted(int(key) for key in metrics if key.isdecimal())
        axes[1].plot(
            np.array(widths) / 1e6,
            [metrics[str(width)] for width in widths],
            marker=marker,
            label=split.capitalize(),
        )
    axes[1].set(
        xlabel="Centered physical bandwidth (MHz)",
        ylabel="Median held FFT phase R",
        ylim=(0, 1),
        title="Training-frozen spectral masks",
    )
    axes[1].legend(frameon=False)
    fig.suptitle(f"Guarded bandwidth comparison · {len(held)}/96 acquired evaluation visits")
    fig.supxlabel(
        "No fitted phase intercept. Frequency and rate use training only; "
        "phase concentration is not calibrated absolute phase.",
        fontsize=9,
    )
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"{prefix}.{suffix}", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=HERE / "guarded-spectral-v4.jsonl")
    parser.add_argument("--prefix", default="guarded-spectral-summary")
    args = parser.parse_args()
    main(args.input, args.prefix)
