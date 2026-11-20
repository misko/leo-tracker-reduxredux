"""Plot only the excluded-date TLE forecast residuals and lock the report artifacts."""

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
    score = json.loads((HERE / "catalogue-scores.json").read_bytes())
    with gzip.open(HERE / "catalogue-pairs.jsonl.gz", "rt") as stream:
        rows = [row for row in map(json.loads, stream) if row["proxy_phase_s"] is not None]
    fig, (errors, signs) = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    dates, x, width = list(score["by_date"]), np.arange(len(score["by_date"])), 0.35
    for i, (name, label, color) in enumerate(
        (
            ("zero", "Zero mean", "#52658a"),
            ("signed", "Causal signed mean", "#087f85"),
        )
    ):
        errors.bar(
            x + (i - 0.5) * width,
            [score["by_date"][d][name]["rms_s"] for d in dates],
            width=width,
            label=label,
            color=color,
        )
    errors.set(
        xticks=x,
        xticklabels=[d[5:] for d in dates],
        xlabel="Held epoch in 2026 (UTC date)",
        ylabel="RMS against later revision (s)",
        title="Directional forecast vs zero",
    )
    errors.legend()
    xx = np.array([row["mean_phase_s"] for row in rows])
    yy = np.array([row["proxy_phase_s"] for row in rows])
    signs.scatter(xx, yy, s=6, c="#087f85", alpha=0.2, edgecolors="none")
    signs.plot([-15, 15], [-15, 15], ls="--", lw=1, c="#52658a", label="Exact agreement")
    signs.axhline(0, lw=0.6, color="0.65")
    signs.axvline(0, lw=0.6, color="0.65")
    signs.set(
        xscale="symlog",
        yscale="symlog",
        xlim=(-18, 18),
        xlabel="Causal phase forecast (s)",
        ylabel="First later-epoch timing correction (s)",
        title=f"{len(rows):,} disjoint satellite/date pairs",
    )
    signs.legend(loc="upper left", fontsize=8)
    fig.savefig(HERE / "catalogue-forecast-skill.png", dpi=170)
    plt.close(fig)
    files = sorted(p for p in HERE.iterdir() if p.is_file() and p.name != "artifact-lock.json")
    (HERE / "artifact-lock.json").write_text(
        json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    main()
