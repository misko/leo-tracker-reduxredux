"""Reconcile all source and target panels before geographic comparison."""

import hashlib
import json
import math
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

plan = json.loads((HERE / "plan.json").read_text())
separate = HERE.parent / "2026_09_28_covariance_position"
old_scores = json.loads((separate / "scores.json").read_text())
old_cross_path = HERE.parent / "2026_09_28_cross_dataset_position/scores.json"
old_cross = json.loads(old_cross_path.read_text())
bindings = {}
for path in [HERE / "input-seal.json", *HERE.glob("t*/**/seal.json")]:
    for name, sha in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == sha
        bindings[name] = sha
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
reference_bindings = old_scores["reference_bindings"]
references = set()
for name, sha in reference_bindings.items():
    path = ROOT / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    if "/pose/" in name:
        pose = json.loads(path.read_text())["pose_authority"]
        references.add((pose["latitude_deg"], pose["longitude_deg"]))
assert len(references) == 1
reference = next(iter(references))


def distance(estimate, coordinate=reference):
    value = horizontal_error_m(estimate["latitude_deg"], estimate["longitude_deg"], *coordinate)

    def vector(lat, lon):
        lat, lon = math.radians(lat), math.radians(lon)
        return np.array(
            [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        )

    a, b = vector(estimate["latitude_deg"], estimate["longitude_deg"]), vector(*coordinate)
    other = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(value - other) < 1e-4
    return value


def selected(parent, stage):
    selection = json.loads((parent / f"{stage}-selection.json").read_text())
    eligible = []
    for run in selection["runs"]:
        path = parent / f"{stage}_fit" / run["start_id"]
        assert int((path / "exit-code.txt").read_text()) == run["exit_code"]
        fit = run["result"]
        if fit is not None:
            assert fit == json.loads((path / "result.json").read_text())
            values = fit["x"][2:] if stage == "target" else fit["x"]
            limits = [5] * len(values) if stage == "target" else [12, 12] + [5] * (len(values) - 2)
            boundary = any(abs(v) > b - 0.001 for v, b in zip(values, limits, strict=True))
            assert fit["qualified"] == bool(
                fit["success"] and not boundary and max(abs(g) for g in fit["gradient"]) <= 0.01
            )
            if fit["qualified"]:
                eligible.append(fit)
    expected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    assert selection["selected"] == expected
    return selection, eligible


def comparison(parent, stage, chosen, groups, decay):
    folder = parent / f"{stage}_held"
    if not folder.exists():
        return {"state": "not_run"}
    code = int((folder / "exit-code.txt").read_text())
    if code:
        return {"state": "failed", "exit_code": code}
    result = json.loads((folder / "result.json").read_text())
    assert abs(result["training_log_score"] - chosen["training_log_score"]) < 1e-7
    assert (
        abs(sum(r["training_log_score"] for r in result["rows"]) - result["training_log_score"])
        < 1e-7
    )
    assert abs(sum(r["held_log_score"] for r in result["rows"]) - result["held_log_score"]) < 1e-7
    details = []
    for group in groups:
        ds = group["dataset_id"]
        covariance = json.loads((separate / ds / f"t{decay}/diagnostic/result.json").read_text())
        old_cov = {(r["session_id"], r["track_id"]): r for r in covariance["rows"]}
        iid = json.loads((ROOT / group["source_point_path"]).read_text())
        old_iid = {
            (r["session_id"], t["track_id"]): t
            for r in iid["evaluation"]
            for rx in r["receivers"]
            for t in rx["tracks"]
        }
        rows = [r for r in result["rows"] if r["session_id"] in group["session_ids"]]
        assert {(r["session_id"], r["track_id"]) for r in rows} == set(old_cov) == set(old_iid)
        assert sum(r["held_observations"] for r in rows) == sum(
            r["held_observations"] for r in covariance["rows"]
        )
        record_deltas = []
        for session in group["session_ids"]:
            current = [r for r in rows if r["session_id"] == session]
            record_deltas.append(
                {
                    "session_id": session,
                    "vs_same_model_panel": sum(
                        r["held_log_score"] - old_cov[(session, r["track_id"])]["held_log_score"]
                        for r in current
                    ),
                    "vs_original_iid_panel": sum(
                        r["held_log_score"] - old_iid[(session, r["track_id"])]["held_log_score"]
                        for r in current
                    ),
                }
            )
        details.append(
            {
                "dataset": ds,
                "tracks": len(rows),
                "held_observations": sum(r["held_observations"] for r in rows),
                "held_delta_vs_same_model_panel": sum(
                    r["vs_same_model_panel"] for r in record_deltas
                ),
                "held_delta_vs_original_iid_panel": sum(
                    r["vs_original_iid_panel"] for r in record_deltas
                ),
                "positive_records_vs_same_model": sum(
                    r["vs_same_model_panel"] > 0 for r in record_deltas
                ),
                "record_deltas": record_deltas,
            }
        )
    return {
        "state": "returned",
        "datasets": details,
        "gradient_check": result["position_gradient_check"],
        "offset_stationarity": result["offset_stationarity"],
    }


rows = []
for spec in plan["models"]:
    decay = spec["decay_s"]
    for unit in spec["units"]:
        parent = HERE / f"t{decay}" / unit["unit_id"]
        selection, eligible = selected(parent, "source")
        chosen = selection["selected"]
        row = {
            "decay_s": decay,
            "unit_id": unit["unit_id"],
            "source_datasets": unit["source_datasets"],
            "excluded_dataset": unit["excluded_dataset"],
            "planned_starts": len(unit["starts"]),
            "qualified_starts": len(eligible),
            "selected": chosen,
        }
        row["source_runs"] = selection["runs"]
        row["higher_score_unqualified_starts"] = [
            {
                "start_id": r["start_id"],
                "training_score_advantage": r["result"]["training_log_score"]
                - chosen["training_log_score"],
                "max_abs_gradient": max(abs(g) for g in r["result"]["gradient"]),
            }
            for r in selection["runs"]
            if chosen is not None
            and r["result"] is not None
            and not r["result"]["qualified"]
            and r["result"]["training_log_score"] > chosen["training_log_score"]
        ]
        if chosen is not None:
            row["error_m"] = distance(chosen["estimate"])
            row["start_separation_m"] = max(
                distance(
                    a["estimate"], (b["estimate"]["latitude_deg"], b["estimate"]["longitude_deg"])
                )
                for a in eligible
                for b in eligible
            )
            source_groups = [
                g for g in spec["groups"] if g["dataset_id"] in unit["source_datasets"]
            ]
            assert chosen["session_ids"] == unit["session_ids"]
            row["source_held"] = comparison(parent, "source", chosen, source_groups, decay)
            if unit["excluded_dataset"] is not None:
                target_selection, targets = selected(parent, "target")
                target = target_selection["selected"]
                row["target_qualified_starts"] = len(targets)
                row["target_selected"] = target
                if target is not None:
                    assert target["x"][:2] == chosen["x"][:2]
                    target_groups = [
                        g for g in spec["groups"] if g["dataset_id"] == unit["excluded_dataset"]
                    ]
                    assert target["session_ids"] == target_groups[0]["session_ids"]
                    row["target_held"] = comparison(parent, "target", target, target_groups, decay)
        rows.append(row)
scores = {
    "rows": rows,
    "reference": reference,
    "execution_bindings_verified": len(bindings),
    "reference_bindings": reference_bindings,
    "iid_cross_dataset_errors": {r["unit_id"]: r["horizontal_error_m"] for r in old_cross["rows"]},
}
previous_path = HERE.parent / "2026_09_28_covariance_transfer/scores.json"
previous_scores = json.loads(previous_path.read_text())
for row in rows:
    old = next(
        r
        for r in previous_scores["rows"]
        if r["decay_s"] == row["decay_s"] and r["unit_id"] == row["unit_id"]
    )
    spec = next(m for m in plan["models"] if m["decay_s"] == row["decay_s"])
    unit = next(u for u in spec["units"] if u["unit_id"] == row["unit_id"])
    seed = unit["refinement_seed"]
    row["refinement_seed"] = seed
    row["previous_qualified_error_m"] = old["error_m"]
    if row["selected"] is not None:
        assert row["selected"]["training_log_score"] >= seed["training_log_score"] - 1e-7
        row["movement_from_seed_m"] = distance(
            row["selected"]["estimate"],
            (seed["estimate"]["latitude_deg"], seed["estimate"]["longitude_deg"]),
        )
        row["movement_from_previous_selection_m"] = distance(
            row["selected"]["estimate"],
            (
                old["selected"]["estimate"]["latitude_deg"],
                old["selected"]["estimate"]["longitude_deg"],
            ),
        )
        row["training_gain_from_seed"] = (
            row["selected"]["training_log_score"] - seed["training_log_score"]
        )
        row["error_change_from_previous_selection_m"] = row["error_m"] - old["error_m"]
        for side in ("source_held", "target_held"):
            if side in row and row[side]["state"] == "returned":
                for ds in row[side]["datasets"]:
                    before = next(d for d in old[side]["datasets"] if d["dataset"] == ds["dataset"])
                    ds["held_change_from_previous_selection"] = (
                        ds["held_delta_vs_same_model_panel"]
                        - before["held_delta_vs_same_model_panel"]
                    )

(HERE / "scores.json").write_text(json.dumps(scores, indent=2, allow_nan=False) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(14, 5), layout="constrained")
units = ["all24", "exclude_DS7", "exclude_DS8", "exclude_DS9"]
xs = np.arange(4)
axes[0].bar(
    xs - 0.25,
    [scores["iid_cross_dataset_errors"][u] for u in units],
    width=0.25,
    label="Original iid",
)
for dx, decay, label in ((0, 0, "Shared scale"), (0.25, 10, "10-second correlation")):
    selected_rows = [
        next(r for r in rows if r["decay_s"] == decay and r["unit_id"] == u) for u in units
    ]
    color = "tab:orange" if decay == 0 else "tab:green"
    axes[0].bar(
        xs + dx,
        [r.get("error_m", np.nan) for r in selected_rows],
        width=0.25,
        label=label,
        color=color,
    )
    changes = [
        r.get("target_held", {})
        .get("datasets", [{}])[0]
        .get("held_delta_vs_same_model_panel", np.nan)
        for r in selected_rows[1:]
    ]
    axes[1].bar(np.arange(3) + dx - 0.125, changes, width=0.25, label=label, color=color)
axes[0].set_xticks(xs, ["All 24", "Without DS7", "Without DS8", "Without DS9"])
axes[0].set_ylabel("Nominal error against unsurveyed reference (m)")
axes[0].axhline(1000, color="black", ls="--", lw=0.8)
axes[0].set_title("Pooled and donor-position geography")
axes[1].set_xticks(np.arange(3), ["DS7", "DS8", "DS9"])
axes[1].set_ylabel("Target held change vs same-model own-panel fit (nats)")
axes[1].axhline(0, color="black", lw=0.8)
axes[1].set_title("Transfer to the excluded dataset")
for ax in axes:
    ax.legend(fontsize=8)
fig.suptitle(
    "Training-only source positions; target timing/offset adaptation at fixed donor position"
)
fig.savefig(HERE / "covariance-transfer.png", dpi=170)
fig.savefig(HERE / "covariance-transfer.svg")
print(json.dumps(scores, indent=2))
