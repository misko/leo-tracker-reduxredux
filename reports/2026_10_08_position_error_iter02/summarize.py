"""Summarize the fixed diagnostic set, never cherry-pick by variant outcome."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
LABELS = ["S10", "S16", "S24", "DS17-004", "DS17-045", "DS17-048", "DS17-051"]
VARIANTS = ["matched-control", "rx-rf-50", "rx-rf-150", "rx-rf-500"]


def main():
    documents = {
        label: json.loads((HERE / "probes" / f"{label}.json").read_text()) for label in LABELS
    }
    rows = {
        (label, row["variant"], row["arm"]): row
        for label, doc in documents.items()
        for row in doc["candidates"]
    }
    summary = {
        "labels": LABELS,
        "scope": "purposely selected development diagnostics",
        "arms": {},
        "nonstationary": [],
    }
    for arm in ["fitted-c", "zero-c"]:
        paired = [
            label
            for label in LABELS
            if all(rows[label, variant, arm]["converged"] for variant in VARIANTS)
        ]
        summary["arms"][arm] = {"paired_labels": paired, "variants": {}}
        for variant in VARIANTS:
            selected = [rows[label, variant, arm] for label in paired]
            summary["arms"][arm]["variants"][variant] = {
                "mean_error_km": float(np.mean([r["error_km"] for r in selected])),
                "mean_posterior_rms_hz": float(np.mean([r["posterior_rms_hz"] for r in selected])),
                "worst_error_km": max(r["error_km"] for r in selected),
            }
            for label in LABELS:
                if not rows[label, variant, arm]["converged"]:
                    summary["nonstationary"].append([label, variant, arm])
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), layout="constrained")
    x = np.arange(len(LABELS))
    for index, variant in enumerate(VARIANTS):
        data = [rows[label, variant, "fitted-c"] for label in LABELS]
        axes[0].bar(x + (index - 1.5) * 0.2, [r["error_km"] for r in data], 0.2, label=variant)
        axes[1].bar(x + (index - 1.5) * 0.2, [r["posterior_rms_hz"] for r in data], 0.2)
    axes[0].axhline(1, color="black", linestyle="--", linewidth=1)
    axes[0].set_ylabel("Position error (km)")
    axes[0].legend(ncol=4)
    axes[1].set_ylabel("Posterior frequency RMS (Hz)")
    for ax in axes:
        ax.set_xticks(x, LABELS)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "Receiver-specific RF calibration: seven development diagnostics\n"
        "Matched candidate bank, start and budget; fitted-c arm"
    )
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
