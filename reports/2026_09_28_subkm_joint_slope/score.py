"""Score only sealed fit outputs against the unchanged DS7 roof reference."""

import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402

seal = json.loads((HERE / "fit-seal.json").read_text())
for name, expected in seal["sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
authority_path = ROOT / "reports/2026_09_27_ds7_post_ds6/pose-authority.json"
authority = json.loads(authority_path.read_text())
index = json.loads(
    (ROOT / "reports/2026_09_27_ds7_full88/residual/independent-response-index.json").read_text()
)
rows = []


def error(estimate):
    return horizontal_error_m(
        estimate["latitude_deg"],
        estimate["longitude_deg"],
        authority["latitude_deg"],
        authority["longitude_deg"],
    )


for ordinal in range(1, 9):
    unit = f"single-{ordinal:03d}"
    folder = HERE / "results" / unit
    receipt = HERE / "receipts" / unit
    row = {"unit_id": unit, "exit_code": int((receipt / "exit-code.txt").read_text())}
    old_response = json.loads(Path(index["responses"][ordinal - 1]["response_path"]).read_text())
    row["historical_error_m"] = error(old_response["estimate"])
    historical_path = folder / "historical.json"
    historical = json.loads(historical_path.read_text()) if historical_path.exists() else None
    row["held_observations"] = historical["held_observations"] if historical else None
    arms = {}
    for arm in ("baseline", "slope"):
        path = folder / f"{arm}.json"
        if not path.exists():
            row[arm] = {"status": "missing", "qualified": False}
            continue
        result = json.loads(path.read_text())
        assert result["unit_id"] == unit
        selected = result["selected"]
        if selected is None:
            row[arm] = {"status": "no_successful_start", "qualified": False}
            continue
        assert selected == max(
            (s for s in result["starts"] if s["success"]), key=lambda s: s["training_log_score"]
        )
        evaluation = result["evaluation"]
        assert math.isclose(
            sum(t["held_log_score"] for t in evaluation["tracks"]),
            evaluation["held_log_score"],
            abs_tol=1e-8,
        )
        row[arm] = {
            "status": "returned",
            "qualified": selected["qualified"],
            "boundary_hit": selected["boundary_hit"],
            "error_m": error(result["estimate"]),
            "estimate": result["estimate"],
            "x": selected["x"],
            "training_log_score": selected["training_log_score"],
            "held_log_score": evaluation["held_log_score"],
            "gradient": selected["gradient"],
            "successful_starts": sum(s["success"] for s in result["starts"]),
            "max_start_position_separation_km": max(
                math.dist(a["x"][:2], b["x"][:2])
                for a in result["starts"]
                for b in result["starts"]
            ),
        }
        arms[arm] = result
    row["paired_qualified"] = row["exit_code"] == 0 and all(
        row[a]["qualified"] for a in ("baseline", "slope")
    )
    if len(arms) == 2:
        before, after = arms["baseline"]["evaluation"], arms["slope"]["evaluation"]
        assert [t["track_id"] for t in before["tracks"]] == [t["track_id"] for t in after["tracks"]]
        gain = after["held_log_score"] - before["held_log_score"]
        row.update(
            error_change_m=row["slope"]["error_m"] - row["baseline"]["error_m"],
            held_gain=gain,
            held_gain_per_observation=gain / row["held_observations"],
            training_gain=after["training_log_score"] - before["training_log_score"],
            map_changes=sum(
                a["map"] != b["map"] for a, b in zip(before["tracks"], after["tracks"], strict=True)
            ),
        )
    rows.append(row)


def aggregate(panel):
    paired = [r for r in panel if "error_change_m" in r]
    return {
        "paired_returned": len(paired),
        "baseline_median_error_m": statistics.median(r["baseline"]["error_m"] for r in paired)
        if paired
        else None,
        "slope_median_error_m": statistics.median(r["slope"]["error_m"] for r in paired)
        if paired
        else None,
        "median_paired_error_change_m": statistics.median(r["error_change_m"] for r in paired)
        if paired
        else None,
        "error_improved": sum(r["error_change_m"] < 0 for r in paired),
        "baseline_below_1km": sum(r["baseline"]["error_m"] < 1000 for r in paired),
        "slope_below_1km": sum(r["slope"]["error_m"] < 1000 for r in paired),
        "positive_held_records": sum(r["held_gain"] > 0 for r in paired),
        "pooled_held_gain": sum(r["held_gain"] for r in paired),
        "equal_record_mean_held_gain_per_observation": statistics.mean(
            r["held_gain_per_observation"] for r in paired
        )
        if paired
        else None,
    }


output = {
    "attempted_records": 8,
    "rows": rows,
    "all_returned": aggregate(rows),
    "paired_qualified": aggregate([r for r in rows if r["paired_qualified"]]),
    "fit_seal_sha256": hashlib.sha256((HERE / "fit-seal.json").read_bytes()).hexdigest(),
    "authority_sha256": hashlib.sha256(authority_path.read_bytes()).hexdigest(),
    "reference_status": (
        "Operator supplied, unsurveyed, exposed single site; altitude and uncertainty unknown."
    ),
    "selection": "Training only; scoring after fit-output seal.",
}
with (HERE / "scores.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
positions = np.arange(8)
for offset, arm, color in [(-0.18, "baseline", "#347c91"), (0.18, "slope", "#c99742")]:
    values = [r[arm].get("error_m", float("nan")) / 1000 for r in rows]
    axes[0].bar(positions + offset, values, width=0.34, label=arm, color=color)
axes[0].axhline(1, color="black", linestyle=":", linewidth=0.8)
axes[0].set(ylabel="Horizontal error (km)", title="Paired individual-record positions")
axes[0].legend()
gains = [r.get("held_gain_per_observation", float("nan")) for r in rows]
axes[1].bar(positions, gains, color=["#3b917d" if g > 0 else "#bd6656" for g in gains])
axes[1].axhline(0, color="black", linewidth=0.8)
axes[1].set(ylabel="Slope minus baseline (held nats / observation)", title="Predictive comparison")
for axis in axes:
    axis.set(
        xticks=positions,
        xticklabels=[f"{i:03d}" for i in range(1, 9)],
        xlabel="Chronological DS7 record",
    )
fig.suptitle("Paired local joint refits — exposed, unsurveyed site")
fig.savefig(HERE / "joint_slope.png", dpi=170)
fig.savefig(HERE / "joint_slope.svg")
print(json.dumps({k: v for k, v in output.items() if k != "rows"}, indent=2))
