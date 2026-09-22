"""Visualize frozen-position diagnostic losses; no geographic-error selection."""

import argparse
import hashlib
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    with open(args.input) as stream:
        document = json.load(stream)
    checksum = document.pop("content_digest")
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if checksum != "sha256:" + hashlib.sha256(encoded.encode()).hexdigest():
        raise ValueError("diagnostic content digest mismatch")
    if document.get("truth_accessed") is not False:
        raise ValueError("truth-free diagnostic required")
    keys = ("result", "sensitivity_per_session_receiver", "sensitivity_weak_receiver_prior")
    labels = ("Shared RX slope · 500 Hz/h prior", "RX slope per scan · 500 Hz/h prior",
              "Shared RX slope · 50,000 Hz/h prior")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    for ax, key, label in zip(axes, keys, labels, strict=True):
        models = document[key]["models"]
        x = np.arange(len(models))
        for shift, field, name in ((-.2, "training_loss", "Training"),
                                   (.2, "heldout_loss", "Held out")):
            values = [m[field] for m in models]
            bars = ax.bar(x + shift, values, width=.4, label=name)
            ax.bar_label(bars, fmt="%.1f", fontsize=8)
        ax.set_xticks(x, ["Offsets", "RX drift", "Orbit proxy", "Joint"], rotation=25)
        ax.set_title(label, fontsize=10)
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("Episode-balanced robust loss · lower is better")
    axes[-1].legend()
    fig.suptitle(
        "Frozen location and soft identities · legacy 250 Hz residual scale\n"
        "Prediction diagnostic only; no new position estimate or calibrated orbit correction"
    )
    fig.tight_layout(rect=(0, 0, 1, .9))
    fig.savefig(args.output, dpi=140)
