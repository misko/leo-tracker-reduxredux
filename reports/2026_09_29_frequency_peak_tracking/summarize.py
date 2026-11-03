"""Audit peak comparisons and expose weak-evidence frame patterns."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = Path(__file__).resolve().parent


def main():
    d = json.loads((BASE / "results.json").read_text())
    for path, expected in d["input_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    assert len(d["rows"]) == 800 and len(d["series"]) == 1280
    names = list(dict.fromkeys(r["signal"] for r in d["rows"]))
    assert len(names) == 8
    assert {(r["signal"], r["receiver"], r["frame"]) for r in d["rows"]} == {
        (n, rx, f) for n in names for rx in [0, 1] for f in range(30, 80)
    }
    summary = []
    for name in names:
        rows = [r for r in d["rows"] if r["signal"] == name]
        series = [r for r in d["series"] if r["signal"] == name]
        a = np.array([r["nmse"]["legacy"] for r in rows])
        b = np.array([r["nmse"]["global_peak"] for r in rows])
        large = [
            r
            for r in rows
            if abs(r["frequencies"]["legacy"] - r["frequencies"]["global_peak"]) > 1000
        ]
        weak_large = sum(
            next(s for s in series if (s["receiver"], s["frame"]) == (r["receiver"], r["frame"]))[
                "candidates"
            ][0]["score"]
            < 0.2
            for r in large
        )
        summary.append(
            dict(
                signal=name,
                count=len(rows),
                legacy_median=float(np.median(a)),
                global_median=float(np.median(b)),
                median_paired_gain=float(np.median(a - b)),
                mean_paired_gain=float(np.mean(a - b)),
                changes_over_1khz=len(large),
                weak_changes=weak_large,
                causal_changes=sum(r["causal_changed"] for r in rows),
                weak_frames={
                    str(rx): [
                        s["frame"]
                        for s in series
                        if s["receiver"] == rx and s["candidates"][0]["score"] < 0.2
                    ]
                    for rx in [0, 1]
                },
            )
        )
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), constrained_layout=True)
    for ax, name in zip(axes, ["S31", "S32"], strict=True):
        for rx in [0, 1]:
            s = [r for r in d["series"] if r["signal"] == name and r["receiver"] == rx]
            ax.plot(
                [r["frame"] for r in s],
                [r["candidates"][0]["score"] for r in s],
                label=f"RX{rx}",
                alpha=0.75,
            )
        ax.axhline(0.2, color="gray", linestyle="--", label="Frozen continuity reset threshold")
        ax.axvline(30, color="#aa7733", linestyle=":")
        ax.set(title=name, xlabel="Relative frame index", ylabel="Best explained pilot energy")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.15)
    fig.suptitle("Both receivers lose pilot evidence on matching frame slots")
    fig.savefig(BASE / "pilot-support.png", dpi=150)
    plt.close(fig)
    print(
        "Verified 800 evaluations and input hashes; causal changes:",
        sum(r["causal_changes"] for r in summary),
    )
    print(
        "Large changed estimates:",
        sum(r["changes_over_1khz"] for r in summary),
        "all weak:",
        sum(r["weak_changes"] for r in summary),
    )


if __name__ == "__main__":
    main()
