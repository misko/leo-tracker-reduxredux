"""Independently replay candidate arithmetic and compare frozen DS9 associations."""

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
plan = json.loads((HERE / "plan.json").read_text())
bindings = {}
for dataset in ("DS7", "DS8", "DS9"):
    seal = json.loads((HERE / "results" / dataset / "fit-seal.json").read_text())
    for name, expected in seal["sha256"].items():
        assert name not in bindings or bindings[name] == expected
        bindings[name] = expected
for name, expected in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name


def lse(values):
    maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def summarize(tracks):
    paired = [t for t in tracks if t["runner_up_catalogue_id"] is not None]
    high = [t for t in paired if t["map_probability"] >= 0.99]
    return {
        "tracks": len(tracks),
        "tracks_with_alternative": len(paired),
        "high_concentration_tracks": len(high),
        "runner_up_held_wins": sum(t["runner_up_held_minus_map"] > 0 for t in paired),
        "high_concentration_runner_up_held_wins": sum(
            t["runner_up_held_minus_map"] > 0 for t in high
        ),
        "alternative_mixture_held_wins": sum(
            t["alternative_mixture_held_minus_full"] > 0 for t in paired
        ),
        "sum_alternative_mixture_held_minus_full": sum(
            t["alternative_mixture_held_minus_full"] for t in paired
        ),
        "median_training_gap": statistics.median(t["training_gap"] for t in paired)
        if paired
        else None,
    }


records, rows_by_unit, checked = [], {}, 0
for member in plan:
    path = HERE / "results" / member["dataset_id"] / (member["unit_id"] + ".json")
    record = {
        "unit_id": member["unit_id"],
        "dataset_id": member["dataset_id"],
        "session_id": member["session_id"],
    }
    if not path.exists():
        record["state"] = (
            member["state"] if member["state"] != "ready" else "audit_failed_or_timed_out"
        )
        records.append(record)
        continue
    row = json.loads(path.read_text())
    assert row["unit_id"] == member["unit_id"] and row["session_id"] == member["session_id"]
    for track in row["tracks"]:
        ids = np.asarray(track["candidate_ids"])
        train = np.array([v if v is not None else -np.inf for v in track["training_scores"]])
        held = np.asarray(track["held_scores"])
        ranks = sorted(np.flatnonzero(np.isfinite(train)), key=lambda i: (-train[i], int(ids[i])))
        normal = lse(train)
        assert int(ids[ranks[0]]) == track["map_catalogue_id"]
        assert np.allclose(np.exp(train - normal), track["weights"], rtol=0, atol=1e-10)
        full = lse(train + held) - normal
        assert abs(full - track["full_held_log_score"]) < 1e-8
        if len(ranks) > 1:
            assert int(ids[ranks[1]]) == track["runner_up_catalogue_id"]
            assert abs(held[ranks[1]] - held[ranks[0]] - track["runner_up_held_minus_map"]) < 1e-8
            rest = ranks[1:]
            alternative = lse(train[rest] + held[rest]) - lse(train[rest])
            assert abs(alternative - full - track["alternative_mixture_held_minus_full"]) < 1e-8
        checked += 1
    assert math.isclose(
        sum(t["full_held_log_score"] for t in row["tracks"]),
        member["expected_held_score"],
        abs_tol=1e-8,
        rel_tol=0,
    )
    rows_by_unit[member["unit_id"]] = row
    record.update(state="complete", **summarize(row["tracks"]))
    records.append(record)
aggregates = {}
for dataset in ("DS7", "DS8", "DS9"):
    subset = [r for r in records if r["dataset_id"] == dataset]
    complete = [r for r in subset if r["state"] == "complete"]
    tracks = [t for r in complete for t in rows_by_unit[r["unit_id"]]["tracks"]]
    aggregates[dataset] = {
        "planned_records": 8,
        "completed_records": len(complete),
        **summarize(tracks),
        "equal_record_mean_runner_up_win_fraction": statistics.mean(
            r["runner_up_held_wins"] / r["tracks_with_alternative"] for r in complete
        )
        if complete
        else None,
    }

parent = ROOT / "reports/2026_09_28_ds89_baseline_panel"
parent_index = json.loads((parent / "evidence-sha256.json").read_text())
joint_dir = parent / "joint/DS9"
for filename in ("request.json", "response.json", "held-evaluation.json"):
    path = joint_dir / filename
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest() == parent_index[str(path.relative_to(ROOT))]
    )
response = json.loads((joint_dir / "response.json").read_text())
assert response["converged"] and not response["boundary_hit"]
joint_request = json.loads((joint_dir / "request.json").read_text())
joint_input = {r["session_id"]: r for r in joint_request["inputs"]}
joint_evals = {
    r["session_id"]: r["evaluation"]
    for r in json.loads((joint_dir / "held-evaluation.json").read_text())
}
joint_comparisons = []
for member in (r for r in plan if r["dataset_id"] == "DS9"):
    if member["unit_id"] not in rows_by_unit:
        continue
    request = json.loads((ROOT / member["request_path"]).read_text())
    assert request["inputs"][0] == joint_input[member["session_id"]]
    independent = rows_by_unit[member["unit_id"]]["tracks"]
    joint = joint_evals[member["session_id"]]["tracks"]
    assert [t["track_id"] for t in independent] == [t["track_id"] for t in joint]
    details = []
    for a, b in zip(independent, joint, strict=True):
        assert len(a["candidate_ids"]) == len(b["weights"])
        weights = np.asarray(b["weights"])
        assert abs(weights.sum() - 1) < 1e-10
        catalogue = a["candidate_ids"][int(np.argmax(weights))]
        details.append(
            {
                "track_id": a["track_id"],
                "independent_catalogue_id": a["map_catalogue_id"],
                "joint_catalogue_id": catalogue,
                "map_changed": catalogue != a["map_catalogue_id"],
                "joint_minus_independent_held_score": b["held_log_score"]
                - a["full_held_log_score"],
            }
        )
    joint_comparisons.append(
        {
            "unit_id": member["unit_id"],
            "tracks": len(details),
            "map_changes": sum(t["map_changed"] for t in details),
            "details": details,
        }
    )
audit = {
    "status": "pass",
    "bindings": len(bindings),
    "track_arithmetic_checks": checked,
    "completed_records": len(rows_by_unit),
    "planned_records": len(plan),
}
output = {
    "aggregates": aggregates,
    "records": records,
    "ds9_joint_comparison": joint_comparisons,
    "audit": audit,
    "scope": "Conditional shortlist discrimination; no physical identity labels.",
}
with (HERE / "summary.json").open("x") as f:
    json.dump(output, f, indent=2, allow_nan=False)
fig, ax = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
for i, dataset in enumerate(("DS7", "DS8", "DS9")):
    a = aggregates[dataset]
    for j, (num, den, color) in enumerate(
        (
            (a["runner_up_held_wins"], a["tracks_with_alternative"], "#397b91"),
            (
                a["high_concentration_runner_up_held_wins"],
                a["high_concentration_tracks"],
                "#c28a36",
            ),
        )
    ):
        percent = 100 * num / den if den else 0
        bar = ax.bar(
            i + (j - 0.5) * 0.32,
            percent,
            width=0.3,
            color=color,
            label=("All comparable tracks" if j == 0 else "Training MAP weight ≥99%")
            if i == 0
            else None,
        )
        ax.bar_label(bar, labels=[f"{num}/{den}"], padding=3, fontsize=10)
ax.set(
    xticks=np.arange(3),
    xticklabels=["DS7: 8 records", "DS8: 7/8 available", "DS9: 8 records"],
    ylabel="Training runner-up wins on held data (%)",
    title="Conditional candidate ranking reversals",
)
ax.set_ylim(0, max(10, ax.get_ylim()[1] * 1.15))
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
fig.savefig(HERE / "candidate-ranking.png", dpi=170)
fig.savefig(HERE / "candidate-ranking.svg")
print(
    json.dumps(
        {
            "aggregates": aggregates,
            "audit": audit,
            "ds9_map_changes": sum(r["map_changes"] for r in joint_comparisons),
        },
        indent=2,
    )
)
