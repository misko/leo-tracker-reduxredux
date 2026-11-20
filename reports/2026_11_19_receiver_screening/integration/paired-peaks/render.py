"""Plot measured pair calibration and orbital-search pruning from sealed results."""

import gzip
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    with gzip.open(HERE / "positions.jsonl.gz", "rt") as stream:
        data = list(map(json.loads, stream))
    with gzip.open(HERE / "misaligned-position.jsonl.gz", "rt") as stream:
        negative = json.loads(stream.readline())
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), constrained_layout=True)
    labels = [r["id"].replace("-omitted", "\n(omitted)") for r in data] + ["RX1 shifted\nnull"]
    x = np.arange(len(labels))
    phases = [r["result"]["metrics"] for r in (*data, negative)]
    for i, (band, label, color) in enumerate(
        (("0", "Channels 1–4", "#087880"), ("1", "Channels 5–8", "#606a8f"))
    ):
        held = [r["calibration"][band] for r in phases]
        for j, item in enumerate(held):
            if item.get("supported"):
                axes[0].scatter(
                    x[j] + (i - 0.5) * 0.20, item["final_relative_cfo_rms_hz"], color=color, s=26
                )
        axes[0].scatter([], [], color=color, label=label, s=26)
        axes[1].bar(
            x + (i - 0.5) * 0.35,
            [m["near_epoch_both_gated_visits"] for m in held],
            width=0.35,
            color=color,
            label=label,
        )
    axes[0].set(title="Receiver-difference prediction", ylabel="Final relative CFO RMS (Hz)")
    axes[1].set(title="Same-frame coincidence", ylabel="Both-gated near-epoch visits")
    ratios = [
        100 * r["decoded_orbit_lane_phases"] / r["full_orbit_lane_phases"]
        if r.get("full_orbit_lane_phases")
        else 0.0
        for r in phases
    ]
    axes[2].bar(x, ratios, color="#087880")
    axes[2].set(title="Orbital path search", ylabel="Decoded share of dense bank (%)")
    axes[0].legend(fontsize=7)
    axes[1].legend(fontsize=7)
    for ax in axes:
        ax.set_xticks(x, labels, fontsize=7, rotation=48, ha="right")
    fig.savefig(HERE / "paired-observability.png", dpi=165)
    plt.close(fig)
    path = HERE / "artifact-lock.json"
    names = sorted(p for p in HERE.iterdir() if p.is_file() and p != path)
    path.write_text(
        json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in names}, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    main()
