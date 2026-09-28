"""Replay frozen track scores and audit local positional likelihood pressure."""

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CROSS = HERE.parent / "2026_09_28_cross_dataset_position"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_residual_audit import student_t4_log_density  # noqa: E402
from ds789_transfer_audit import summarize  # noqa: E402


def flatten(result):
    rows = {}
    for record in result["evaluation"]:
        for receiver in record["receivers"]:
            for track in receiver["tracks"]:
                key = (record["session_id"], track["track_id"])
                assert key not in rows
                rows[key] = track
    return rows


def replay(track, model, point, stored, *, gradient):
    prediction, visible = model.prediction(track, point)
    offsets = np.asarray(stored["offsets"])
    residual = track["y"][None, :] - prediction - offsets[:, None]
    mask = track["mask"]
    density = student_t4_log_density(residual)
    scores = np.where(visible, density[:, mask].sum(axis=1) - 0.5 * offsets**2 / 1e12, -np.inf)
    normal = float(logsumexp(scores))
    weights = np.exp(scores - normal)
    assert np.allclose(weights, stored["weights"], atol=1e-9, rtol=1e-9)
    assert int(np.argmax(scores)) == stored["map"]
    held = float(logsumexp(scores + density[:, ~mask].sum(axis=1)) - normal)
    assert abs(held - stored["held_log_score"]) <= 1e-8
    derivative = np.zeros(2)
    if gradient:
        influence = 5 * residual[:, mask] / (40000 + residual[:, mask] ** 2)
        for axis in range(2):
            delta = np.zeros(3)
            delta[axis] = 1e-4
            plus, vp = model.prediction(track, point + delta)
            minus, vm = model.prediction(track, point - delta)
            assert np.array_equal(visible, vp) and np.array_equal(visible, vm)
            derivative[axis] = float(
                weights @ np.sum(influence * ((plus - minus) / 2e-4)[:, mask], axis=1)
            )
    return normal - math.log(track["catalogue_size"]), held, derivative


dataset = sys.argv[1]
plan = json.loads((CROSS / "plan.json").read_text())
group = next(g for g in plan["groups"] if g["dataset_id"] == dataset)
original = json.loads((ROOT / group["source_point_path"]).read_text())
all_fit = json.loads((CROSS / "all24/source-selection.json").read_text())["selected"]
all_held = json.loads((CROSS / "all24/source_held/result.json").read_text())
transfer_fit = json.loads((CROSS / f"exclude_{dataset}/target-selection.json").read_text())[
    "selected"
]
transfer_held = json.loads((CROSS / f"exclude_{dataset}/target_held/result.json").read_text())
old_rows = flatten(original)
comparisons = {"all24": (all_fit, all_held), "transfer": (transfer_fit, transfer_held)}
documents = baseline.load_documents({"config": plan["config"], "inputs": group["inputs"]})
assert [d["session_id"] for d in documents] == group["session_ids"]
rows = []
for di, (document, item) in enumerate(zip(documents, group["inputs"], strict=True)):
    model = baseline.Stationary(document, plan["config"])
    session = document["session_id"]
    old_point = np.array(original["x"][:2] + [original["x"][di + 2]])
    manifest = next(
        a for a in item["artifacts"] if a["kind"] == "candidates" and a["path"].endswith(".json")
    )
    bank_path = next(a["path"] for a in item["artifacts"] if a["path"].endswith(".npz"))
    indices = {
        t["track_id"]: t["index"] for t in json.loads(Path(manifest["path"]).read_text())["tracks"]
    }
    with np.load(bank_path, allow_pickle=False) as bank:
        for name, (new_fit, new_held) in comparisons.items():
            new_rows = flatten(new_held)
            ni = new_fit["session_ids"].index(session)
            point = np.array(new_fit["x"][:2] + [new_fit["x"][ni + 2]])
            direction = old_point[:2] - point[:2]
            direction /= np.linalg.norm(direction)
            subtotal = np.zeros(4)
            for track in document["tracks"]:
                key = (session, track["track_id"])
                before, after = old_rows[key], new_rows[key]
                ids = bank[f"candidate_ids_{indices[track['track_id']]}"]
                assert len(ids) == len(before["weights"]) == len(after["weights"])
                a, b, _ = replay(track, model, old_point, before, gradient=False)
                c, d, g = replay(track, model, point, after, gradient=True)
                subtotal += np.array([a, b, c, d])
                rows.append(
                    {
                        "dataset": dataset,
                        "comparison": name,
                        "session_id": session,
                        "track_id": track["track_id"],
                        "receiver": track["receiver_id"],
                        "channel": track["channel"],
                        "training_count": int(track["mask"].sum()),
                        "held_count": int((~track["mask"]).sum()),
                        "span_s": max(track["times_s"]) - min(track["times_s"]),
                        "training_delta": c - a,
                        "held_delta": d - b,
                        "old_training_score": a,
                        "new_training_score": c,
                        "old_held_score": b,
                        "new_held_score": d,
                        "map_before": int(ids[before["map"]]),
                        "map_after": int(ids[after["map"]]),
                        "map_changed": bool(ids[before["map"]] != ids[after["map"]]),
                        "old_map_weight": max(before["weights"]),
                        "new_map_weight": max(after["weights"]),
                        "weight_total_variation": 0.5
                        * sum(
                            abs(x - y)
                            for x, y in zip(before["weights"], after["weights"], strict=True)
                        ),
                        "position_gradient": g.tolist(),
                        "toward_original_gradient": float(g @ direction),
                    }
                )
            old_record = next(r for r in original["evaluation"] if r["session_id"] == session)
            new_record = next(r for r in new_held["evaluation"] if r["session_id"] == session)
            expected = [
                old_record["training_log_score"],
                old_record["held_log_score"],
                new_record["training_log_score"],
                new_record["held_log_score"],
            ]
            assert np.allclose(subtotal, expected, rtol=0, atol=1e-7)
summaries, strata = [], []
for name in comparisons:
    selected = [r for r in rows if r["comparison"] == name]
    assert set((r["session_id"], r["track_id"]) for r in selected) == set(old_rows)
    summaries.append(
        {
            "dataset": dataset,
            "comparison": name,
            **summarize(selected),
            "position_gradient_sum": np.sum(
                [r["position_gradient"] for r in selected], axis=0
            ).tolist(),
        }
    )
    for fields in (("receiver",), ("channel",), ("receiver", "channel"), ("session_id",)):
        for key in sorted({tuple(r[f] for f in fields) for r in selected}):
            subset = [r for r in selected if tuple(r[f] for f in fields) == key]
            strata.append(
                {
                    "dataset": dataset,
                    "comparison": name,
                    "grouping": list(fields),
                    "key": list(key),
                    **summarize(subset),
                }
            )
with (HERE / dataset / "result.json").open("x") as stream:
    json.dump(
        {"summaries": summaries, "strata": strata, "rows": rows}, stream, indent=2, allow_nan=False
    )
print(json.dumps(summaries, indent=2))
