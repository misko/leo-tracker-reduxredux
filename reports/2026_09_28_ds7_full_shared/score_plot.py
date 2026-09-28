"""Verify sealed selections and score both constituent panels separately."""

import hashlib
import json
import math
import re
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
bindings = {}
for path in [HERE / "input-seal.json", *HERE.glob("t*/**/seal.json")]:
    for name, digest in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
references = set()
all_sessions = [r["session_id"] for records in plan["membership"].values() for r in records]
assert len(all_sessions) == len(set(all_sessions)) == 88
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
for unit, group in zip(spec["units"], spec["groups"], strict=True):
    ds = group["dataset_id"]
    assert unit["session_ids"] == group["session_ids"]
    assert unit["source_datasets"] == [ds] and unit["excluded_dataset"] is None
    assert unit["starts"] == [
        {"source_dataset": label, "x": xy + [0] * 88}
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
            abs(v) > b - 0.001 for v, b in zip(fit["x"], [12, 12] + [5] * 88, strict=True)
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
    for label, previous in group["comparisons"].items():
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
        assert len(sessions) == 15 and set(subset) == set(baseline)
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
                "baseline_error_m": distance(oldfit["estimate"]),
                "tracks": len(subset),
                "held_observations": sum(v["held_observations"] for v in subset.values()),
                "training_delta": sum(r["training_log_score"] for r in deltas),
                "held_delta": sum(r["held_log_score"] for r in deltas),
                "positive_held_records": sum(r["held_log_score"] > 0 for r in deltas),
                "record_deltas": deltas,
            }
        )
    additional_sessions = {
        r["session_id"] for r in plan["membership"][ds] if r["panel"] == "additional58"
    }
    assert len(additional_sessions) == 58
    additional = {k: v for k, v in current.items() if k[0] in additional_sessions}
    assert not accounted.intersection(additional) and accounted | set(additional) == set(current)
    row["additional58"] = {
        "records": 58,
        "tracks": len(additional),
        "held_observations": sum(v["held_observations"] for v in additional.values()),
        "training_log_score": sum(v["training_log_score"] for v in additional.values()),
        "held_log_score": sum(v["held_log_score"] for v in additional.values()),
        "comparison": "No prior shared-scale fit for these records",
    }
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
    assert (len(current), train_count, held_count) == (5131, 143207, 95894)
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
fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
assert len(rows) == 1
row = rows[0]
names = [a["start"] for a in row["alternatives"]]
values = [a.get("error_m", np.nan) for a in row["alternatives"]]
colors = [
    "tab:orange" if a.get("fit", {}).get("qualified") else "lightgray" for a in row["alternatives"]
]
if "panels" in row:
    names.append("Prior 30")
    values.append(row["panels"][0]["baseline_error_m"])
    colors.append("tab:blue")
axes[0].bar(names, values, color=colors)
if row["selected"]:
    axes[0].scatter(
        names.index(row["selected"]["start_id"]),
        row["error_m"],
        marker="*",
        s=160,
        color="black",
        label="Training-selected",
    )
axes[0].axhline(1000, color="black", ls="--", lw=0.8)
axes[0].set_ylabel("Nominal error against unsurveyed reference (m)")
axes[0].set_title("All88 DS7: three generic starts")
axes[0].legend(fontsize=8)
panels = row.get("panels", [])
axes[1].bar([p["panel"] for p in panels], [p["held_delta"] for p in panels])
axes[1].axhline(0, color="black", lw=0.8)
axes[1].set_ylabel("Held change on original30 vs their prior fit (nats)")
axes[1].set_title("Matched original-panel prediction")
fig.savefig(HERE / "full-ds7.png", dpi=170)
fig.savefig(HERE / "full-ds7.svg")
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
