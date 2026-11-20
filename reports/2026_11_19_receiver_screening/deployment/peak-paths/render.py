"""Show measured path throughput and fitted/held RF without mixing c arms."""

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
    with gzip.open(HERE / "positions.jsonl.gz", "rt") as value:
        data = list(map(json.loads, value))
    with gzip.open(HERE / "shuffle-position.jsonl.gz", "rt") as value:
        shuffled = json.loads(value.readline())
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), constrained_layout=True)
    stages = [*data, shuffled]
    k = np.arange(len(stages))
    label = [
        r["id"].replace("-omitted", "\n(omitted)").replace("-shuffle", "\n(shuffle)")
        for r in stages
    ]
    axes[0].bar(k, [r["result"]["metrics"]["selected_paths"] for r in stages], color="#087780")
    axes[0].set(ylabel="Disjoint training paths", title="Native visit support")
    for ax, arm in zip(axes[1:], ("c0", "fitted_c"), strict=True):
        for j, (field, legend, color) in enumerate(
            (
                ("rf_rms_hz", "Training RMS", "#617a9f"),
                ("held_rms_hz", "Held RMS", "#087780"),
            )
        ):
            y = [r["result"]["arms"][arm].get(field) for r in stages]
            ax.scatter(k + (j - 0.5) * 0.20, y, label=legend, color=color, s=26)
        ax.set(
            ylabel="Conditional RF residual RMS (Hz)", title="c = 0" if arm == "c0" else "Fitted c"
        )
        ax.legend(fontsize=7, loc="upper left")
    for ax in axes:
        ax.set_xticks(k, label, rotation=48, ha="right", fontsize=7)
        ax.axvline(7.5, color=".65", lw=1)
        ax.axvline(9.5, color=".65", lw=1)
    fig.savefig(HERE / "path-support.png", dpi=160)
    plt.close(fig)
    path = HERE / "artifact-lock.json"
    files = sorted(p for p in HERE.rglob("*") if p.is_file() and p != path)
    path.write_text(
        json.dumps(
            {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
