"""Scientific summary figure of independently verified recurring code families."""

import csv
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main():
    out = Path(__file__).parent / "local"
    result = json.loads((out / "joint-results.json").read_text())
    rows = list(csv.DictReader((out / "decoded-bits.csv").open()))
    groups = [g for g in result["groups"] if g["qualified_codes"]]
    families = sorted({r["family"] for r in rows})
    counts = np.array(
        [
            [sum(r["group"] == g["group"] and r["family"] == f for r in rows) for f in families]
            for g in groups
        ]
    )
    fig, ax = plt.subplots(figsize=(13, 5.5), layout="constrained")
    im = ax.imshow(counts, aspect="auto", cmap="Blues", vmin=0)
    for i, j in zip(*np.nonzero(counts), strict=True):
        ax.text(
            j,
            i,
            str(counts[i, j]),
            ha="center",
            va="center",
            fontsize=9,
            color="white" if counts[i, j] > counts.max() / 2 else "black",
        )
    ax.set_yticks(
        np.arange(len(groups)),
        [
            f"{g['dataset']} {g['group']}  |  "
            f"NORAD {g['norad_id'] if g['norad_id'] else 'unresolved'}"
            for g in groups
        ],
    )
    ax.set_xticks(np.arange(len(families)), [str(i + 1) for i in range(len(families))])
    ax.set_xlabel(
        "60-bit code family (rotation / polarity normalized; numbering local to this figure)"
    )
    ax.set_title(
        "DS7 + DS8: code families recur across visits and likely satellite identities\n"
        "Only codewords independently agreeing on both receivers; identities are orbital inferences"
    )
    fig.colorbar(im, ax=ax, label="Verified frames")
    fig.savefig(out / "code-family-comparison.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
