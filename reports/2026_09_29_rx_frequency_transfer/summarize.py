"""Validate transfer evidence and visualize within-visit RX differences."""

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
    assert len(result["visits"]) == 8 and len(result["rows"]) == 800
    summary = []
    fig, axes = plt.subplots(4, 2, figsize=(11, 10), constrained_layout=True)
    for v, ax in zip(result["visits"], axes.ravel(), strict=True):
        f = np.array(v["frequencies"])
        assert f.shape == (2, 80)
        offset = float(np.median(f[1, :30] - f[0, :30]))
        assert offset == v["offset_hz"]
        residual = f[1] - f[0] - offset
        assert float(np.median(abs(residual[30:]))) == v["held_difference_residual_median_abs_hz"]
        rows = [r for r in result["rows"] if r["signal"] == v["signal"]]
        assert {(r["receiver"], r["frame"]) for r in rows} == {
            (rx, n) for rx in [0, 1] for n in range(30, 80)
        }
        metrics = []
        for rx in [0, 1]:
            s = [r for r in rows if r["receiver"] == rx]
            own = np.array([r["nmse"]["own"] for r in s])
            blend = np.array([r["nmse"]["blend"] for r in s])
            shuffled = np.array([r["nmse"]["shuffled"] for r in s])
            zero = np.array([r["nmse"]["zero_offset"] for r in s])
            metrics.append(
                dict(
                    receiver=rx,
                    count=len(s),
                    own_median=float(np.median(own)),
                    blend_median=float(np.median(blend)),
                    median_paired_gain=float(np.median(own - blend)),
                    blend_wins=int(sum(blend < own)),
                    wins_over_shuffled=int(sum(blend < shuffled)),
                    zero_offset_median=float(np.median(zero)),
                )
            )
        summary.append(
            dict(
                signal=v["signal"],
                dataset=v["dataset"],
                qualified=v["qualified"],
                offset_hz=offset,
                train_mad_hz=v["train_difference_mad_hz"],
                held_residual_hz=v["held_difference_residual_median_abs_hz"],
                train_over_1khz=int(np.sum(abs(residual[:30]) > 1000)),
                held_over_1khz=int(np.sum(abs(residual[30:]) > 1000)),
                held_max_abs_hz=float(np.max(abs(residual[30:]))),
                receivers=metrics,
            )
        )
        ax.plot(np.arange(80) / 750 * 1000, residual, color="#287b9b", linewidth=1)
        ax.axvline(30 / 750 * 1000, color="#b56d24", linestyle="--", label="Evaluation begins")
        ax.axhline(0, color="gray", linewidth=0.7)
        ax.set(
            title=v["signal"],
            xlabel="Relative frame time (ms)",
            ylabel="RX difference residual (Hz)",
        )
        ax.grid(alpha=0.15)
    fig.suptitle("Past-only RX offset: later residual differences remain")
    fig.savefig(BASE / "rx-differences.png", dpi=140)
    plt.close(fig)
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for qualified in [False, True]:
        s = [r for r in summary if not qualified or r["qualified"]]
        ms = [m for r in s for m in r["receivers"]]
        print(
            "qualified" if qualified else "all",
            "wins",
            sum(m["blend_wins"] for m in ms),
            "/",
            sum(m["count"] for m in ms),
            "positive RX groups",
            sum(m["median_paired_gain"] > 0 for m in ms),
            "/",
            len(ms),
        )
    print("All hashes, offset estimates and exact 800-row membership verified.")


if __name__ == "__main__":
    main()
