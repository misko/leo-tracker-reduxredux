"""Audit frozen shadow exports and summarize the chronological transfer panel."""

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
request = json.loads(
    (ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/request.json").read_text()
)
rows = []
binding_count = 0
for ordinal in range(2, 9):
    unit = f"single-{ordinal:03d}"
    receipt = HERE / "receipts" / unit
    for name, expected in json.loads((receipt / "launch.json").read_text())["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
        binding_count += 1
    assert (receipt / "exit-code.txt").read_text().strip() == "0"
    result = json.loads((HERE / "results" / f"{unit}.json").read_text())
    assert result["unit_id"] == unit
    assert result["session_id"] == request["inputs"][ordinal - 1]["session_id"]
    old = json.loads(
        (ROOT / f"reports/2026_09_28_subkm_residual_transfer/results/{unit}.json").read_text()
    )
    assert result["held_observations"] == old["joint"]["held_observations"]
    for new_key, old_key in [
        ("training_log_score", "training_log_score"),
        ("held_log_score", "held_predictive_log_density"),
    ]:
        assert math.isclose(result["zero"][new_key], old["joint"][old_key], rel_tol=0, abs_tol=1e-8)
    regimes = []
    for regime in result["regimes"]:
        before, after = result["zero"]["tracks"], regime["evaluation"]["tracks"]
        gains, tv = [], []
        for a, b in zip(before, after, strict=True):
            assert a["track_id"] == b["track_id"]
            for track in (a, b):
                assert math.isclose(sum(track["weights"]), 1, abs_tol=1e-10)
            gains.append(b["held_log_score"] - a["held_log_score"])
            tv.append(
                0.5 * sum(abs(x - y) for x, y in zip(a["weights"], b["weights"], strict=True))
            )
        assert math.isclose(math.fsum(gains), regime["held_gain"], rel_tol=0, abs_tol=1e-8)
        assert math.isclose(np.mean(tv), regime["mean_candidate_total_variation"], abs_tol=1e-12)
        assert regime["selected"] == max(
            (c for c in regime["candidates"] if c["success"]), key=lambda c: c["training_log_score"]
        )
        slope = regime["selected"]["slope_native_hz_s"]
        bound = regime["bound_native_hz_s"]
        ordered = sorted(gains, reverse=True)
        regimes.append(
            {
                "bound": bound,
                "slope_native_hz_s": slope,
                "held_gain": regime["held_gain"],
                "held_gain_per_observation": regime["held_gain"] / result["held_observations"],
                "training_gain": regime["evaluation"]["training_log_score"]
                - result["zero"]["training_log_score"],
                "converged_starts": sum(c["success"] for c in regime["candidates"]),
                "boundary_hit": bound is not None and abs(slope) >= bound - 1e-6,
                "tracks": len(gains),
                "positive_tracks": sum(g > 0 for g in gains),
                "map_changes": regime["map_changes"],
                "mean_candidate_total_variation": float(np.mean(tv)),
                "top_two_gain": sum(ordered[:2]),
                "other_tracks_gain": sum(ordered[2:]),
                "per_track_gains": gains,
            }
        )
    for check in result["gradient_checks"]:
        assert abs(check["analytic"] - check["finite_difference"]) <= 1e-4 + 1e-4 * abs(
            check["finite_difference"]
        )
    rows.append(
        {
            "unit_id": unit,
            "session_id": result["session_id"],
            "held_observations": result["held_observations"],
            "regimes": regimes,
            "fixed_position_profile_curvature": result["fixed_position_profile_curvature"],
            "conditional_curvature_standard_error": result["conditional_curvature_standard_error"],
        }
    )
primary = [r["regimes"][0] for r in rows]
gains = [r["held_gain_per_observation"] for r in primary]
first = json.loads((ROOT / "reports/2026_09_28_subkm_shared_slope/results.json").read_text())
first_gain = first["regimes"][0]["held_gain"]
first_n = json.loads(
    (ROOT / "reports/2026_09_28_subkm_residual_transfer/results/single-001.json").read_text()
)["joint"]["held_observations"]
summary = {
    "status": "complete",
    "recordings": rows,
    "source_binding_checks": binding_count,
    "primary_seven": {
        "equal_record_mean_gain_per_held_observation": float(np.mean(gains)),
        "pooled_held_gain": sum(r["held_gain"] for r in primary),
        "positive_records": sum(g > 0 for g in gains),
        "records": 7,
        "held_observations": sum(r["held_observations"] for r in rows),
    },
    "descriptive_eight_including_exposed_first": {
        "equal_record_mean_gain_per_held_observation": (sum(gains) + first_gain / first_n) / 8,
        "pooled_held_gain": sum(r["held_gain"] for r in primary) + first_gain,
        "positive_records": sum(g > 0 for g in gains) + int(first_gain > 0),
    },
    "scope": (
        "Exported arithmetic, identity and source checks; "
        "not an independent fitter or geographic result."
    ),
}
with (HERE / "summary.json").open("x") as stream:
    json.dump(summary, stream, indent=2, allow_nan=False)
fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
labels = [r["unit_id"].replace("single-", "") for r in rows]
axes[0].bar(labels, gains, color=["#3b917d" if g > 0 else "#bd6656" for g in gains])
axes[0].axhline(0, color="black", linewidth=0.8)
axes[0].set(
    xlabel="Chronological DS7 recording",
    ylabel="Held gain (nats / observation)",
    title="Primary ±20 native Hz/s model",
)
for index, (label, marker) in enumerate([("±20", "o"), ("±40", "s"), ("Unbounded", "x")]):
    axes[1].plot(
        labels,
        [r["regimes"][index]["slope_native_hz_s"] for r in rows],
        marker=marker,
        label=label,
        alpha=0.75,
    )
axes[1].axhline(0, color="black", linewidth=0.8)
axes[1].set(
    xlabel="Chronological DS7 recording",
    ylabel="Training-fitted slope (native Hz/s)",
    title="Computational-bound sensitivity",
)
axes[1].legend()
fig.suptitle("Shared slope transfer: fixed position and timing; no new location fit")
fig.savefig(HERE / "slope_transfer.png", dpi=170)
fig.savefig(HERE / "slope_transfer.svg")
print(json.dumps({k: v for k, v in summary.items() if k != "recordings"}, indent=2))
