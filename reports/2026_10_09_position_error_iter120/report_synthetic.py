"""Read sealed synthetic results; no estimator calls."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    protocol = HERE / "synthetic-protocol.json"
    plan = json.loads(protocol.read_text())
    result = json.loads((HERE / "synthetic-result.json").read_text())
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    assert result["protocol_sha256"] == digest
    for path, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    expected = {
        (a, c, s) for a in plan["amplitudes"] for c in plan["cutoffs_s"] for s in plan["seeds"]
    }
    rows = result["rows"]
    assert result["status"] == "complete" and result["native_calls"] == len(rows) == 160
    assert {(r["amplitude"], r["cutoff_s"], r["seed"]) for r in rows} == expected
    for row in rows:
        assert row["passed"] == (row["margin"] >= 0.025)
        assert abs(row["margin"] - row["exact"] + row["control"]) < 1e-14
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for amplitude, color in zip(plan["amplitudes"], ["#176b9a", "#ba501c"], strict=True):
        groups = [g for g in result["groups"] if g["amplitude"] == amplitude]
        x = np.array([g["occupancy"] for g in groups])
        y = np.array([g["pass_fraction"] for g in groups])
        low = np.maximum(0, y - [g["wilson95"][0] for g in groups])
        high = np.maximum(0, np.array([g["wilson95"][1] for g in groups]) - y)
        axes[0].errorbar(
            x, y, yerr=[low, high], fmt="o-", capsize=3, color=color, label=f"Amplitude {amplitude}"
        )
        rms = []
        for group in groups:
            values = [
                r["residual_cfo_hz"]
                for r in rows
                if r["amplitude"] == amplitude
                and r["cutoff_s"] == group["cutoff_s"]
                and r["passed"]
            ]
            rms.append(float(np.sqrt(np.mean(np.square(values)))) if values else np.nan)
        axes[1].plot(x, rms, "o-", color=color, label=f"Amplitude {amplitude}")
    axes[0].plot([0, 1], [0, 1], "--", color="0.5", label="Linear occupancy hypothesis")
    axes[0].set(ylabel="Conditional margin-pass fraction (Wilson 95%)", ylim=(-0.05, 1.05))
    axes[1].set(ylabel="Passed-only residual CFO RMS (Hz)")
    for axis in axes:
        axis.set_xlabel("Fraction of pilot samples before signal turn-off")
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    fig.suptitle("Synthetic conditioned native GLRT · 16 noise seeds per cell · no acquisition")
    fig.savefig(HERE / "synthetic-occupancy.png", dpi=160)
    plt.close(fig)
    elapsed = np.array([r["elapsed_s"] for r in rows])
    verification = {
        "status": "verified",
        "rows": len(rows),
        "source_files": len(plan["source_sha256"]),
        "failed_calls": 0,
        "native_seconds": float(elapsed.sum()),
        "native_median_ms": float(np.median(elapsed) * 1000),
        "native_max_ms": float(elapsed.max() * 1000),
        "sha256": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in [
                "synthetic-protocol.json",
                "synthetic-result.json",
                "synthetic-presence.so.build.json",
                "synthetic-presence.so",
            ]
        },
    }
    assert verification["sha256"]["synthetic-presence.so"] == result["library_sha256"]
    (HERE / "synthetic-verification.json").write_text(json.dumps(verification, indent=2))
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
