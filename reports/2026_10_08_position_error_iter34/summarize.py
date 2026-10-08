"""Render frozen pair audit; offset histograms are explicitly post-hoc."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    hist, hx = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    table = [
        "| Scan | sigma (s) | Start | c | Pairs ≤250 Hz | Null ≤250 Hz |",
        "|---|---:|---|---|---:|---:|",
    ]
    peaks = {}
    for k, label in enumerate(plan["labels"]):
        data = json.loads((HERE / "results" / f"{label}.json").read_text())
        n = data["coverage"]["singleton_pairs"]
        assert n == data["coverage"]["null_eligible_pairs"]
        assert all(abs(p["time_separation_s"]) <= 0.001 for p in data["pairs"])
        assert all(abs(p["null_separation_s"]) >= 30 for p in data["pairs"])
        for row in data["candidates"]:
            a = np.asarray(row["residual_hz"])
            b = np.asarray(row["null_residual_hz"])
            assert len(a) == len(b) == n
            table.append(
                f"| {label} | {row['relative_sigma_s']} | "
                f"{row['initialization']} | {row['arm']} | "
                f"{sum(abs(a) <= 250)}/{n} | {sum(abs(b) <= 250)}/{n} |"
            )
        for j, arm in enumerate(("fitted-c", "zero-c")):
            ax = axes[k, j]
            rows = [r for r in data["candidates"] if r["arm"] == arm]
            for row in rows:
                y = np.arange(1, n + 1) / n
                (line,) = ax.plot(
                    np.sort(abs(np.asarray(row["residual_hz"]))),
                    y,
                    label=f"σ={row['relative_sigma_s']}, {row['initialization']}",
                )
                ax.plot(
                    np.sort(abs(np.asarray(row["null_residual_hz"]))),
                    y,
                    color=line.get_color(),
                    linestyle="--",
                    alpha=0.6,
                )
            ax.set(
                xscale="symlog",
                xlim=(0, 115000),
                ylim=(0, 1),
                title=f"{label} / {arm}",
                xlabel="Absolute residual (Hz)",
                ylabel="Fraction",
            )
            ax.axvline(250, color="grey", linewidth=0.8)
            ax.legend(fontsize=7)
        row = next(
            r
            for r in data["candidates"]
            if r["arm"] == "fitted-c"
            and r["relative_sigma_s"] == 2
            and r["initialization"] == "original-start"
        )
        bins = np.arange(-113750, 114251, 500)
        a, _ = np.histogram(row["residual_hz"], bins)
        b, _ = np.histogram(row["null_residual_hz"], bins)
        centers = (bins[:-1] + bins[1:]) / 2
        top = np.argsort(a)[-5:][::-1]
        peaks[label] = [
            dict(center_hz=float(centers[i]), coincident=int(a[i]), null=int(b[i])) for i in top
        ]
        for j, limits in enumerate(((-114000, 114000), (-15000, 15000))):
            hx[k, j].step(centers, a, where="mid", label="Coincident")
            hx[k, j].step(centers, b, where="mid", label="Mismatched time", alpha=0.7)
            hx[k, j].set(
                xlim=limits,
                title=label,
                xlabel="Signed residual (Hz)",
                ylabel="Pairs per 500 Hz bin",
            )
            hx[k, j].legend()
    fig.suptitle("Receiver-pair residual CDF: solid coincident, dashed mismatched-time control")
    hist.suptitle("Post-hoc offset histogram: original start, sigma 2 s, fitted c")
    fig.savefig(HERE / "pair-cdf.png", dpi=150)
    hist.savefig(HERE / "offset-histogram.png", dpi=150)
    (HERE / "pair-counts.md").write_text("\n".join(table) + "\n")
    (HERE / "posthoc-peaks.json").write_text(json.dumps(peaks, indent=2) + "\n")
    print(f"Verified {len(plan['source_sha256'])} frozen hashes and both pair cohorts")


if __name__ == "__main__":
    main()
