"""Verify complete membership, fallback accounting and immutable input bindings."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    result = json.loads((BASE / "results.json").read_text())
    for path, expected in result["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    rows = result["rows"]
    expected = {
        (name, rx, frame)
        for name in ["S02", "S31", "S32", "S13", "S28", "S29", "DS9-middle", "DS9-first"]
        for rx in [0, 1]
        for frame in range(12)
    }
    assert len(rows) == len(expected) == 192
    assert {(r["signal"], r["receiver"], r["frame"]) for r in rows} == expected
    for r in rows:
        arm = "hybrid" if r["qualified"] else "pilot"
        assert r["arms"]["gated"] == r["arms"][arm]
    summary = []
    for name in dict.fromkeys(r["signal"] for r in rows):
        subset = [r for r in rows if r["signal"] == name]
        by_rx = {
            rx: sorted([r for r in subset if r["receiver"] == rx], key=lambda r: r["frame"])
            for rx in [0, 1]
        }
        agreement = sum(a["state"] == b["state"] for a, b in zip(by_rx[0], by_rx[1], strict=True))
        metrics = {}
        for key in ["held_pilot_nmse", "held_sequence_nmse"]:
            a = np.array([r["arms"]["pilot"][key] for r in subset])
            b = np.array([r["arms"]["gated"][key] for r in subset])
            q = np.array([r["qualified"] for r in subset])
            metrics[key] = dict(
                pilot_median=float(np.median(a)),
                gated_median=float(np.median(b)),
                median_paired_gain=float(np.median(a - b)),
                wins=int(sum(b < a)),
                ties=int(sum(b == a)),
                qualified_median_paired_gain=float(np.median((a - b)[q])) if q.any() else None,
            )
        summary.append(
            dict(
                signal=name,
                dataset=subset[0]["dataset"],
                count=len(subset),
                qualified=sum(r["qualified"] for r in subset),
                rx_state_agreement=agreement,
                metrics=metrics,
            )
        )
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    names = [r["signal"] for r in summary]
    axes[0].bar(names, [r["qualified"] for r in summary], color="#267a9c")
    axes[0].set(
        ylabel="Qualified receiver-frames / 24", ylim=(0, 25), title="Sequence availability"
    )
    gains = [r["metrics"]["held_pilot_nmse"]["qualified_median_paired_gain"] for r in summary]
    axes[1].bar(names, [v if v is not None else np.nan for v in gains], color="#488b68")
    axes[1].axhline(0, color="gray", linewidth=1)
    axes[1].set(
        ylabel="Median paired NMSE reduction", title="Held-pilot gain, qualified subset only"
    )
    for ax in axes:
        ax.tick_params(axis="x", rotation=50)
        ax.grid(axis="y", alpha=0.15)
    fig.suptitle("Longer sequence support: modest gains and limited coverage")
    fig.savefig(BASE / "comparison.png", dpi=160)
    plt.close(fig)
    print("All 192 inputs, fallback decisions and source bindings verified.")
    for row in summary:
        print(row["signal"], row["qualified"], row["metrics"]["held_pilot_nmse"])


if __name__ == "__main__":
    main()
