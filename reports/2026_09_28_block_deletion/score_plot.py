"""Verify sealed selections and score both constituent panels separately."""

import hashlib
import json
import math
import re
import sys
from collections import Counter
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
bindings = {}
for path in [HERE / "input-seal.json", *HERE.glob("t*/**/seal.json")]:
    for name, digest in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
references = set()
all_sessions = [r["session_id"] for records in plan["membership"].values() for r in records]
assert len(all_sessions) == 360 and len(set(all_sessions)) == 90
assert set(Counter(all_sessions).values()) == {4}
previous_plan = json.loads((HERE.parent / "2026_09_28_combined30/plan.json").read_text())
assert plan["config"] == previous_plan["config"]
for records in plan["membership"].values():
    for record in records:
        pose = json.loads((ROOT / record["pose_path"]).read_text())["pose_authority"]
        references.add((pose["latitude_deg"], pose["longitude_deg"]))
assert len(references) == 1
reference = next(iter(references))


def distance(estimate):
    lat, lon = estimate["latitude_deg"], estimate["longitude_deg"]
    result = horizontal_error_m(lat, lon, *reference)

    def vector(lat, lon):
        lat, lon = math.radians(lat), math.radians(lon)
        return np.array(
            [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        )

    a, b = vector(lat, lon), vector(*reference)
    check = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(result - check) < 1e-4
    return result


rows = []
spec = plan["models"][0]
assert len(plan["models"]) == 1 and spec["decay_s"] == 0
assert len(spec["units"]) == len(spec["groups"]) == 15
for unit, group in zip(spec["units"], spec["groups"], strict=True):
    ds = group["dataset_id"]
    original = previous_plan["membership"][group["source_dataset"]]
    block = group["block"]
    assert group["omitted"] == original[6 * block : 6 * (block + 1)]
    assert plan["membership"][ds] == original[: 6 * block] + original[6 * (block + 1) :]
    assert group["session_ids"] == [r["session_id"] for r in plan["membership"][ds]]
    original_group = next(
        g
        for g in previous_plan["models"][0]["groups"]
        if g["dataset_id"] == group["source_dataset"]
    )
    original_inputs = {i["session_id"]: i for i in original_group["inputs"]}
    assert group["inputs"] == [original_inputs[s] for s in group["session_ids"]]
    assert len(group["inputs"]) == 24 and len(group["omitted"]) == 6
    assert unit["session_ids"] == group["session_ids"]
    assert unit["source_datasets"] == [ds] and unit["excluded_dataset"] is None
    assert unit["starts"] == [
        {"source_dataset": label, "x": xy + [0] * 24}
        for label, xy in (("origin", [0, 0]), ("southeast", [3, -3]), ("northwest", [-3, 3]))
    ]
    parent = HERE / "t0" / unit["unit_id"]
    selection = json.loads((parent / "source-selection.json").read_text())
    eligible, alternatives = [], []
    for run in selection["runs"]:
        folder = parent / "source_fit" / run["start_id"]
        assert int((folder / "exit-code.txt").read_text()) == run["exit_code"]
        fit = run["result"]
        if fit is None:
            assert run["exit_code"] != 0
            alternatives.append({"start": run["start_id"], "exit_code": run["exit_code"]})
            continue
        assert fit == json.loads((folder / "result.json").read_text())
        assert fit["initial"] == next(
            s["x"] for s in unit["starts"] if s["source_dataset"] == run["start_id"]
        )
        assert fit["session_ids"] == group["session_ids"]
        boundary = any(
            abs(v) > b - 0.001 for v, b in zip(fit["x"], [12, 12] + [5] * 24, strict=True)
        )
        assert fit["qualified"] == bool(
            fit["success"] and not boundary and max(map(abs, fit["gradient"])) <= 0.01
        )
        if fit["qualified"]:
            eligible.append(fit)
        alternatives.append(
            {"start": run["start_id"], "error_m": distance(fit["estimate"]), "fit": fit}
        )
    chosen = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    assert selection["selected"] == chosen and selection["qualified_starts"] == len(eligible)
    row = {
        "dataset": ds,
        "source_dataset": group["source_dataset"],
        "block": block,
        "omitted": group["omitted"],
        "qualified_starts": len(eligible),
        "selected": chosen,
        "alternatives": alternatives,
    }
    if chosen is None:
        rows.append(row)
        continue
    held_path = parent / "source_held"
    assert int((held_path / "exit-code.txt").read_text()) == 0
    held = json.loads((held_path / "result.json").read_text())
    assert abs(held["training_log_score"] - chosen["training_log_score"]) < 1e-7
    for field in ("training_log_score", "held_log_score"):
        assert abs(sum(r[field] for r in held["rows"]) - held[field]) < 1e-7
    assert len(held["position_gradient_check"]) == 4
    assert max(g["absolute_difference"] for g in held["position_gradient_check"]) < 0.002
    current = {(r["session_id"], r["track_id"]): r for r in held["rows"]}
    assert len(current) == len(held["rows"])
    assert {k[0] for k in current} == set(group["session_ids"])
    panels = []
    accounted = set()
    for label in ("union", "outside"):
        previous = group["comparison"]
        old = json.loads((ROOT / previous / "source_held/result.json").read_text())
        oldfit = json.loads((ROOT / previous / "source-selection.json").read_text())["selected"]
        sessions = {r["session_id"] for r in plan["membership"][ds] if r["panel"] == label}
        subset = {k: v for k, v in current.items() if k[0] in sessions}
        full_baseline = {(r["session_id"], r["track_id"]): r for r in old["rows"]}
        baseline = {k: v for k, v in full_baseline.items() if k[0] in sessions}
        assert oldfit["qualified"] and len(full_baseline) == len(old["rows"])
        assert abs(old["training_log_score"] - oldfit["training_log_score"]) < 1e-7
        for field in ("training_log_score", "held_log_score"):
            assert abs(sum(r[field] for r in full_baseline.values()) - old[field]) < 1e-7
        assert set(subset) == set(baseline)
        assert not accounted.intersection(subset)
        accounted.update(subset)
        assert all(
            v["held_observations"] == baseline[k]["held_observations"] for k, v in subset.items()
        )
        deltas = [
            {
                "session_id": sid,
                **{
                    field: sum(
                        v[field] - baseline[k][field] for k, v in subset.items() if k[0] == sid
                    )
                    for field in ("training_log_score", "held_log_score")
                },
            }
            for sid in sorted(sessions)
        ]
        panels.append(
            {
                "panel": label,
                "records": len(sessions),
                "baseline_error_m": distance(oldfit["estimate"]),
                "tracks": len(subset),
                "held_observations": sum(v["held_observations"] for v in subset.values()),
                "training_delta": sum(r["training_log_score"] for r in deltas),
                "held_delta": sum(r["held_log_score"] for r in deltas),
                "positive_held_records": sum(r["held_log_score"] > 0 for r in deltas),
                "record_deltas": deltas,
            }
        )
    assert accounted == set(current)
    train_count = held_count = 0
    for item in group["inputs"]:
        artifact = next(a for a in item["artifacts"] if a["kind"] == "observations")
        for track in json.loads(Path(artifact["path"]).read_text())["tracks"]:
            key = item["session_id"], track["track_id"]
            if key in current:
                n = sum(track["training_mask"])
                nh = len(track["training_mask"]) - n
                assert n >= 2 and nh == current[key]["held_observations"]
                train_count += n
                held_count += nh
    row.update(
        error_m=distance(chosen["estimate"]),
        panels=panels,
        tracks=len(current),
        training_observations=train_count,
        held_observations=held_count,
        gradient_check=held["position_gradient_check"],
    )
    rows.append(row)
scores = {"rows": rows, "reference": reference, "execution_bindings_verified": len(bindings)}
(HERE / "scores.json").write_text(json.dumps(scores, indent=2, allow_nan=False) + "\n")
resources = []
for path in sorted(HERE.glob("t*/**/resources.txt")):
    text = path.read_text()
    elapsed = re.search(r"Elapsed \(wall clock\) time.*: (\S+)", text).group(1)
    seconds = 0.0
    for part in elapsed.split(":"):
        seconds = seconds * 60 + float(part)
    resources.append(
        {
            "job": str(path.parent.relative_to(HERE)),
            "wall_s": seconds,
            "max_rss_kib": int(
                re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
            ),
            "exit_code": int((path.parent / "exit-code.txt").read_text()),
        }
    )
(HERE / "resource-summary.json").write_text(
    json.dumps(
        {
            "jobs": resources,
            "total_job_wall_s": sum(r["wall_s"] for r in resources),
            "max_job_wall_s": max(r["wall_s"] for r in resources),
            "max_rss_kib": max(r["max_rss_kib"] for r in resources),
        },
        indent=2,
    )
    + "\n"
)
fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), sharey=True, layout="constrained")
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    subset = [r for r in rows if r["source_dataset"] == ds]
    assert [r["block"] for r in subset] == list(range(5))
    for row in subset:
        for alternative in row["alternatives"]:
            if "error_m" in alternative:
                qualified = alternative["fit"]["qualified"]
                ax.scatter(
                    row["block"] + 1,
                    alternative["error_m"],
                    marker="o" if qualified else "x",
                    color="tab:gray",
                    alpha=0.6,
                )
    ax.plot(
        range(1, 6), [r.get("error_m", np.nan) for r in subset], "o-", label="Training-selected 24"
    )
    baseline = json.loads(
        (
            ROOT
            / next(g["comparison"] for g in spec["groups"] if g["source_dataset"] == ds)
            / "source-selection.json"
        ).read_text()
    )["selected"]
    ax.axhline(distance(baseline["estimate"]), color="tab:green", ls=":", label="Full 30")
    ax.axhline(1000, color="black", ls="--", lw=0.8, label="1 km")
    ax.set_title(ds)
    ax.set_xticks(range(1, 6))
    ax.set_xlabel("Omitted chronological block (6 records)")
    ax.legend(fontsize=8)
axes[0].set_ylabel("Nominal error against unsurveyed reference (m)")
fig.suptitle("Fixed chronological deletion audit; gray points show all starts")
fig.savefig(HERE / "block-errors.png", dpi=170)
fig.savefig(HERE / "block-errors.svg")
print(
    json.dumps(
        {
            "datasets": [
                {k: v for k, v in r.items() if k in ("dataset", "error_m", "qualified_starts")}
                for r in rows
            ],
            "bindings": len(bindings),
        },
        indent=2,
    )
)
