"""Audit complete-panel accounting and render individual versus pooled budgets."""

import hashlib
import json
import math
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE.parent / "2026_09_28_ds89_baseline_transfer"
plan = json.loads((PREFLIGHT / "plan.json").read_text())
scores = json.loads((HERE / "scores.json").read_text())
joint = json.loads((HERE / "joint-scores.json").read_text())
assert [r["unit_id"] for r in scores["rows"]] == [r["unit_id"] for r in plan["captures"]]
bindings = {}
for path in list((HERE / "solver").glob("*/fit-seal.json")) + list(
    (HERE / "joint").glob("*/fit-seal.json")
):
    for name, expected in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == expected
        bindings[name] = expected
for name, expected in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name


def vector(point):
    lat, lon = np.radians([point["latitude_deg"], point["longitude_deg"]])
    return np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


distance_checks = 0
for row in scores["rows"] + joint["rows"]:
    if row["state"] != "scored":
        continue
    dataset = row["dataset_id"]
    source = next(s for s in plan["sources"] if s["dataset_id"] == dataset)
    manifest_path = ROOT / source["path"]
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == source["sha256"]
    sid = row.get(
        "session_id", next(r["session_id"] for r in plan["captures"] if r["dataset_id"] == dataset)
    )
    pose_path = manifest_path.parent / "pose" / (sid + ".json")
    if "pose_file_sha256" in row:
        assert (
            "sha256:" + hashlib.sha256(pose_path.read_bytes()).hexdigest()
            == row["pose_file_sha256"]
        )
    for pose in row.get("pose_bindings", []):
        assert (
            "sha256:" + hashlib.sha256((ROOT / pose["path"]).read_bytes()).hexdigest()
            == pose["sha256"]
        )
    authority = json.loads(pose_path.read_text())["pose_authority"]
    a, b = vector(row["estimate"]), vector(authority)
    error = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(error - row["horizontal_error_m"]) < 1e-4
    assert row["below_1km"] == (row["qualified"] and row["horizontal_error_m"] < 1000)
    distance_checks += 1
for dataset in ("DS8", "DS9"):
    panel = [r for r in scores["rows"] if r["unit_id"].startswith(dataset + "-")]
    assert len(panel) == 8
    returned = [r for r in panel if r["state"] == "scored"]
    qualified = [r for r in returned if r["qualified"]]
    aggregate = scores["aggregates"][dataset]
    assert aggregate["qualified"] == len(qualified)
    assert aggregate["below_1km_qualified"] == sum(r["below_1km"] for r in qualified)
    if qualified:
        assert aggregate["median_qualified_error_m"] == statistics.median(
            r["horizontal_error_m"] for r in qualified
        )
    first = panel[0]
    previous = next(
        r
        for r in json.loads((PREFLIGHT / "scores.json").read_text())["rows"]
        if r["unit_id"] == first["unit_id"]
    )
    assert first["horizontal_error_m"] == previous["horizontal_error_m"]
comparisons = []
for pooled in joint["rows"]:
    if pooled["state"] != "scored":
        continue
    dataset = pooled["dataset_id"]
    panel = [r for r in scores["rows"] if r.get("dataset_id") == dataset]
    evaluations = json.loads((HERE / "joint" / dataset / "held-evaluation.json").read_text())
    assert [r["session_id"] for r in evaluations] == [r["session_id"] for r in panel]
    assert all(r["state"] == "scored" for r in panel)
    deltas = []
    for individual, shared in zip(panel, evaluations, strict=True):
        assert individual["held_observations"] == shared["held_observations"]
        deltas.append(shared["evaluation"]["held_log_score"] - individual["held_log_score"])
    comparisons.append(
        {
            "dataset_id": dataset,
            "joint_minus_individual_held_log_score": sum(deltas),
            "positive_records": sum(d > 0 for d in deltas),
            "paired_records": len(deltas),
            "paired_held_observations": sum(r["held_observations"] for r in panel),
            "equal_record_mean_delta_nats_per_observation": statistics.mean(
                d / r["held_observations"] for d, r in zip(deltas, panel, strict=True)
            ),
            "per_record_deltas": deltas,
        }
    )
audit = {
    "status": "pass",
    "binding_checks": len(bindings),
    "individual_rows": 16,
    "geographic_checks": distance_checks,
    "preflight_results_unchanged": 2,
    "paired_held_comparisons": comparisons,
    "scope": "Independent exported arithmetic and distance formula; no second numerical fit.",
}
path = HERE / "audit-summary.json"
if path.exists():
    assert json.loads(path.read_text()) == audit
else:
    with path.open("x") as stream:
        json.dump(audit, stream, indent=2)
fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True, sharey=True)
for ax, dataset in zip(axes, ("DS8", "DS9"), strict=True):
    panel = [r for r in scores["rows"] if r["unit_id"].startswith(dataset + "-")]
    values = [r.get("horizontal_error_m", float("nan")) / 1000 for r in panel]
    colors = ["#347c91" if r.get("qualified") else "#999999" for r in panel]
    ax.bar(np.arange(8), values, color=colors, label="Individual recording")
    pooled = next(r for r in joint["rows"] if r["dataset_id"] == dataset)
    if pooled["state"] == "scored":
        ax.axhline(
            pooled["horizontal_error_m"] / 1000,
            color="#c58b30",
            linewidth=2,
            label="Shared position, all eight",
        )
    else:
        ax.text(
            0.02,
            0.95,
            "Joint fit unavailable: one input export timed out",
            transform=ax.transAxes,
            va="top",
            fontsize=8,
        )
    ax.axhline(1, color="black", linestyle=":", linewidth=0.8, label="1 km target")
    for i, row in enumerate(panel):
        if row["state"] != "scored":
            ax.text(i, 0.1, "missing", rotation=90, ha="center", va="bottom", fontsize=8)
    ax.set(
        title=dataset,
        xticks=np.arange(8),
        xticklabels=[f"{i:03d}" for i in range(1, 9)],
        xlabel="Chronological recording",
        xlim=(-0.6, 7.6),
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=8)
axes[0].set_ylabel("Horizontal error (km)")
fig.suptitle("Frozen baseline transfer: individual and eight-record pooled budgets")
fig.savefig(HERE / "panel.png", dpi=170)
fig.savefig(HERE / "panel.svg")
print(json.dumps(audit, indent=2))
