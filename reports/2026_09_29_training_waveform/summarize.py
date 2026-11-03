"""Render equal-excerpt comparisons without filtering numerical outcomes."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "results.json").read_text())
    rows = data["rows"]
    lines = [
        "| Dataset | Excerpts returned/planned | Cached NMSE | Short NMSE | Long NMSE | Long beats cached | Long beats short |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for ds in ("DS7", "DS8", "DS9", "all"):
        selected = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        valid = [r for r in selected if r["status"] == "ok"]
        values = np.array(
            [
                [np.mean(r["arms"][a]["frame_nmse"]) for a in ("cached", "short", "long")]
                for r in valid
            ]
        )
        if len(valid):
            means = " | ".join(f"{x:.6f}" for x in values.mean(axis=0))
            wins = [(values[:, 2] < values[:, i]).sum() for i in (0, 1)]
            lines.append(
                f"| {ds} | {len(valid)}/{len(selected)} | {means} | {wins[0]} | {wins[1]} |"
            )
    lines += [
        "",
        "Means weight each excerpt equally; lower NMSE is better.",
        "",
        "| Panel | RX | Status | Cached NMSE | Short NMSE | Long NMSE | Short residual Hz | Long residual Hz |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    valid = []
    for r in rows:
        prefix = f"| {r['unit_id']} | {r['receiver_id']} | {r['status']}"
        if r["status"] != "ok":
            lines.append(prefix + " | — | — | — | — | — |")
            continue
        valid.append(r)
        means = " | ".join(
            f"{np.mean(r['arms'][a]['frame_nmse']):.6f}" for a in ("cached", "short", "long")
        )
        frequencies = " | ".join(
            f"{r['arms'][a]['residual_frequency_hz']:.3f}"
            + (" (bound)" if r["arms"][a]["boundary"] else "")
            for a in ("short", "long")
        )
        lines.append(prefix + f" | {means} | {frequencies} |")
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(10, 6))
    for arm, offset in (("short", -0.16), ("long", 0.16)):
        gains = [
            np.mean(r["arms"]["cached"]["frame_nmse"]) - np.mean(r["arms"][arm]["frame_nmse"])
            for r in valid
        ]
        ax.barh(np.arange(len(valid)) + offset, gains, height=0.3, label=arm)
    ax.set_yticks(np.arange(len(valid)), [f"{r['unit_id']} RX{r['receiver_id']}" for r in valid])
    ax.axvline(0, color="black", linewidth=0.7)
    ax.set_xlabel("Held pilot NMSE reduction versus cached frequency (positive is better)")
    ax.set_title("Frozen training-selected excerpts; eight frames per excerpt")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
