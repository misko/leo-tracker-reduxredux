"""Audit exported slope receipts and plot held track contributions."""

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for name, expected in json.loads((HERE / "launch.json").read_text())["sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
assert (HERE / "exit-code.txt").read_text().strip() == "0"
result = json.loads((HERE / "results.json").read_text())
baseline = result["zero"]["tracks"]
summary = {"status": "pass", "regimes": []}
for regime in result["regimes"]:
    fitted = regime["evaluation"]["tracks"]
    assert len(baseline) == len(fitted) == 56
    gains = []
    tv = []
    for before, after in zip(baseline, fitted, strict=True):
        assert before["track_id"] == after["track_id"]
        assert math.isclose(sum(after["weights"]), 1, abs_tol=1e-10)
        gains.append(after["held_log_score"] - before["held_log_score"])
        tv.append(
            0.5 * sum(abs(a - b) for a, b in zip(before["weights"], after["weights"], strict=True))
        )
    assert math.isclose(math.fsum(gains), regime["held_gain"], abs_tol=1e-8)
    assert math.isclose(sum(tv) / len(tv), regime["mean_candidate_total_variation"], abs_tol=1e-12)
    assert all(c["success"] for c in regime["candidates"])
    summary["regimes"].append(
        {
            "bound": regime["bound_native_hz_s"],
            "slope": regime["selected"]["slope_native_hz_s"],
            "held_gain": math.fsum(gains),
            "positive_tracks": sum(g > 0 for g in gains),
            "per_track_gains": gains,
        }
    )
primary = summary["regimes"][0]
ordered = sorted(primary["per_track_gains"], reverse=True)
summary["primary_top_two_gains"] = sum(ordered[:2])
summary["primary_remainder_gain"] = sum(ordered[2:])
summary["scope"] = (
    "Exported score/weight arithmetic and source integrity; shared fit implementation."
)
with (HERE / "audit-summary.json").open("x") as stream:
    json.dump(summary, stream, indent=2)
fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
axes[0].bar(
    ["±20", "±40", "Unbounded"], [r["held_gain"] for r in summary["regimes"]], color="#427b96"
)
axes[0].set(
    ylabel="Held predictive gain (nats)",
    xlabel="Computational slope bounds (native Hz/s)",
    title="Stable across fitting bounds",
)
gains = np.array(primary["per_track_gains"])
axes[1].bar(np.arange(1, 57), gains, color=np.where(gains > 0, "#3d977c", "#c06b5a"))
axes[1].axhline(0, color="black", linewidth=0.8)
axes[1].set(
    xlabel="Track index in frozen bank",
    ylabel="Held predictive gain (nats)",
    title="24/56 tracks improve; gains are concentrated",
)
fig.suptitle("First-record shared-slope shadow: fixed position, training-only fit")
fig.savefig(HERE / "shared_slope.png", dpi=170)
fig.savefig(HERE / "shared_slope.svg")
print(json.dumps({k: v for k, v in summary.items() if k != "regimes"}, indent=2))
