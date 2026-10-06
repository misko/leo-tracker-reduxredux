"""Build report figures and whole-scan edge contrasts from frozen aggregates."""

import argparse
import json
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = json.loads(args.audit.read_text())
    syn = json.loads(args.synthetic.read_text())
    rng = np.random.default_rng(20261006)

    def passrate(r, key):
        c = r["lanes"][key]["counts"]
        return 100 * c["passing"] / c["probes"]

    def standardized(r):
        return np.mean([passrate(r, k) for k in r["lanes"]])

    def epoch(r):
        return datetime.fromisoformat(r["captured_at"].replace("Z", "+00:00")).timestamp()

    summary = {}
    paired = {}
    for rate in (2500000, 10000000):
        summary[rate] = {}
        for edge in ("lower", "upper"):
            scans = [r for r in rows if r["rate"] == rate and r["edge"] == edge]
            lanes = {
                key: float(np.mean([passrate(r, key) for r in scans])) for key in scans[0]["lanes"]
            }
            count = {
                k: sum(lane["counts"][k] for r in scans for lane in r["lanes"].values())
                for k in scans[0]["lanes"]["1:0"]["counts"]
            }
            quantiles = {
                k: [
                    float(
                        np.mean(
                            [lane["quantiles"][k][i] for r in scans for lane in r["lanes"].values()]
                        )
                    )
                    for i in range(3)
                ]
                for k in scans[0]["lanes"]["1:0"]["quantiles"]
            }
            summary[rate][edge] = dict(
                scans=len(scans),
                lanes=lanes,
                counts=count,
                mean_lane_quantiles=quantiles,
                standardized_pass=float(np.mean(list(lanes.values()))),
            )
        lower = [r for r in rows if r["rate"] == rate and r["edge"] == "lower"]
        upper = [r for r in rows if r["rate"] == rate and r["edge"] == "upper"]
        options = sorted(
            (abs(epoch(low) - epoch(u)), i, j)
            for i, low in enumerate(lower)
            for j, u in enumerate(upper)
        )
        usedl = set()
        usedu = set()
        pairs = []
        for gap, i, j in options:
            if gap > 5400:
                break
            if i in usedl or j in usedu:
                continue
            usedl.add(i)
            usedu.add(j)
            pairs.append((lower[i], upper[j], gap))
        differences = np.array([standardized(u) - standardized(low) for low, u, gap in pairs])
        ci = np.quantile(
            rng.choice(differences, (20000, len(differences)), replace=True).mean(axis=1),
            [0.025, 0.975],
        )
        paired[rate] = dict(
            count=len(pairs),
            median_gap_minutes=float(np.median([p[2] for p in pairs]) / 60),
            upper_minus_lower_pp=float(differences.mean()),
            ci95=ci.tolist(),
            pairs=[
                dict(lower=low["session_id"], upper=u["session_id"], gap_seconds=gap)
                for low, u, gap in pairs
            ],
        )
        print(rate, "PAIR", {k: v for k, v in paired[rate].items() if k != "pairs"})
    (args.output / "edge-summary.json").write_text(
        json.dumps(
            dict(groups=summary, paired=paired, seed=20261006, bootstrap_replicates=20000), indent=2
        )
    )
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.4), layout="constrained")
    for ax, rate in zip(axs, (2500000, 10000000), strict=False):
        delta = np.array(
            [
                [
                    summary[rate]["upper"]["lanes"][f"{ch}:{rx}"]
                    - summary[rate]["lower"]["lanes"][f"{ch}:{rx}"]
                    for ch in (1, 2, 3, 4)
                ]
                for rx in (0, 1)
            ]
        )
        im = ax.imshow(delta, cmap="RdBu", vmin=-15, vmax=15, aspect="auto")
        for rx in range(2):
            for ch in range(4):
                ax.text(
                    ch,
                    rx,
                    f"{delta[rx, ch]:+.1f} pp",
                    ha="center",
                    va="center",
                    color="white" if abs(delta[rx, ch]) > 8 else "black",
                )
        ax.set(
            xticks=range(4),
            xticklabels=["CH1", "CH2", "CH3", "CH4"],
            yticks=[0, 1],
            yticklabels=["RX0", "RX1"],
            title=f"{rate / 1e6:g} MS/s",
        )
    fig.colorbar(im, ax=axs, label="Upper minus lower GLRT passing-probe percentage points")
    fig.suptitle("The upper-edge deficit varies by receiver and channel")
    fig.savefig(args.output / "edge-lanes.png", dpi=180, bbox_inches="tight")
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8), layout="constrained")
    for ax, rate in zip(axs, (2500000, 10000000), strict=False):
        for edge, color in [("lower", "#197a9a"), ("upper", "#cc7c29")]:
            scans = [r for r in rows if r["rate"] == rate and r["edge"] == edge]
            hist = np.sum(
                [lane["cfo_histogram"] for r in scans for lane in r["lanes"].values()], axis=0
            )
            ax.stairs(hist / hist.sum() * 100, np.linspace(-800, 800, 33), color=color, label=edge)
        bound = 429.6875 if rate == 2500000 else 800
        ax.axvline(-bound, color="gray", ls=":")
        ax.axvline(bound, color="gray", ls=":")
        ax.set(
            title=f"{rate / 1e6:g} MS/s",
            xlabel="Acquired CFO relative to nominal pilot (kHz)",
            ylabel="Winner candidates per bin (%)",
        )
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle("Measured acquisition offsets after removing capture tuning")
    fig.savefig(args.output / "edge-cfo.png", dpi=180)
    fig, axs = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    for row, rate in enumerate((2500000, 10000000)):
        for rx in (0, 1):
            ax = axs[row, rx]
            for edge, color in [("lower", "#197a9a"), ("upper", "#cc7c29")]:
                hist = np.sum(
                    [
                        r["lanes"][f"{ch}:{rx}"]["conditional"]["passed"]["cfo_histogram"]
                        for r in rows
                        if r["rate"] == rate and r["edge"] == edge
                        for ch in (1, 2, 3, 4)
                    ],
                    axis=0,
                )
                ax.stairs(
                    hist / hist.sum() * 100, np.linspace(-800, 800, 33), color=color, label=edge
                )
            ax.axvline(-429.6875, color="gray", ls=":")
            ax.axvline(429.6875, color="gray", ls=":")
            ax.set(
                title=f"{rate / 1e6:g} MS/s RX{rx}",
                xlabel="Acquired pilot-relative CFO (kHz)",
                ylabel="Passing winners per bin (%)",
            )
            ax.legend()
            ax.grid(alpha=0.2)
    fig.suptitle(
        "Passing acquisition seeds have different CFO distributions on RX0 and RX1\n"
        "Dotted lines mark the 2.5 MS/s full-template search limits"
    )
    fig.savefig(args.output / "edge-cfo-by-rx.png", dpi=180)
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8), layout="constrained")
    labels = []
    for i, (rate, edge) in enumerate(
        [(r, e) for r in (2500000, 10000000) for e in ("lower", "upper")]
    ):
        samples = [
            r
            for r in syn
            if r["fs"] == rate and r["edge"] == edge and r["noise_to_pilot_db_at_2p5"] is None
        ]
        labels.append(f"{rate / 1e6:g} {edge}")
        real = summary[rate][edge]["mean_lane_quantiles"]
        for ax, exact, control in [
            (
                axs[0],
                np.mean([r["exact"] for r in samples]),
                np.mean([r["control"] for r in samples]),
            ),
            (axs[1], real["exact"][1], real["control"][1]),
        ]:
            ax.bar(
                i - 0.17,
                exact,
                width=0.32,
                color="#197a9a",
                label="Exact template" if i == 0 else None,
            )
            ax.bar(
                i + 0.17,
                control,
                width=0.32,
                color="#cc7c29",
                label="Shifted control" if i == 0 else None,
            )
    for ax, title in zip(
        axs,
        [
            "Noiseless production-template self-consistency check",
            "Real data: mean of lane median winner scores",
        ],
        strict=False,
    ):
        ax.set(xticks=range(4), xticklabels=labels, title=title, ylabel="Normalized score")
        ax.legend()
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("A control-code asymmetry exists, but real deficits are mostly in exact scores")
    fig.savefig(args.output / "edge-score-controls.png", dpi=180)


if __name__ == "__main__":
    main()
