"""Unchanged stationary geographic likelihood with source/target separation."""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_pooled_receiver_slope import PooledReceiverSlope  # noqa: E402

baseline.baseline.profile = baseline.profile
unit_id, stage, start_id = sys.argv[1:]
plan = json.loads((HERE / "plan.json").read_text())
unit = next(u for u in plan["units"] if u["unit_id"] == unit_id)
target = stage.startswith("target")
groups = [
    g
    for g in plan["groups"]
    if (
        g["dataset_id"] == unit["excluded_dataset"]
        if target
        else g["dataset_id"] in unit["source_datasets"]
    )
]
request = {"config": plan["config"], "inputs": [i for g in groups for i in g["inputs"]]}
documents = baseline.load_documents(request)
assert [d["session_id"] for d in documents] == [s for g in groups for s in g["session_ids"]]
model = baseline.JointObjective(documents, plan["config"])
folder = HERE / unit_id / stage
if stage in ("source_fit", "target_fit"):
    folder = folder / start_id
    if target:
        chosen = json.loads((HERE / unit_id / "source-selection.json").read_text())
        position = np.asarray(chosen["selected"]["x"][:2])
        initial = np.full(8, float(start_id))
        bounds = [(-5, 5)] * 8

        def objective(point):
            value, gradient = model.value_gradient(np.r_[position, point])
            return value, gradient[2:]

    else:
        start = next(s for s in unit["starts"] if s["source_dataset"] == start_id)
        initial = np.asarray(start["x"])
        bounds = [(-12, 12)] * 2 + [(-5, 5)] * len(documents)
        objective = model.value_gradient
        offset = 0
        replay = []
        for group in groups:
            local = baseline.JointObjective(documents[offset : offset + 8], plan["config"])
            score = -local.value_gradient(np.asarray(group["point"]))[0]
            assert abs(score - group["training_log_score"]) <= 1e-7
            replay.append({"dataset": group["dataset_id"], "score": score})
            offset += 8
        with (folder / "baseline-replay.json").open("x") as stream:
            json.dump(replay, stream, indent=2)
    fit = minimize(
        objective,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={
            "maxiter": 100 if target else 140,
            "maxfun": 180 if target else 200,
            "ftol": 1e-12,
            "gtol": 1e-6,
            "maxls": 30,
        },
    )
    boundary = any(
        min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    x = np.r_[position, fit.x] if target else fit.x
    result = {
        "unit_id": unit_id,
        "stage": stage,
        "start_id": start_id,
        "initial": initial.tolist(),
        "x": x.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "qualified": bool(fit.success and not boundary and np.max(np.abs(fit.jac)) <= 0.01),
        "evaluations": int(fit.nfev),
        "iterations": int(fit.nit),
        "estimate": dict(zip(("latitude_deg", "longitude_deg"), model.coordinates(x), strict=True)),
        "session_ids": [d["session_id"] for d in documents],
    }
else:
    chosen = json.loads(
        (
            HERE / unit_id / ("target-selection.json" if target else "source-selection.json")
        ).read_text()
    )
    x = np.asarray(chosen["selected"]["x"])
    shadow = PooledReceiverSlope(documents, plan["config"])
    rows = shadow.held(np.r_[x, 0.0, 0.0])
    score = sum(r["training_log_score"] for r in rows)
    assert abs(score - chosen["selected"]["training_log_score"]) <= 1e-7
    result = {
        "unit_id": unit_id,
        "stage": stage,
        "evaluation": rows,
        "training_log_score": score,
        "held_log_score": sum(r["held_log_score"] for r in rows),
    }
with (folder / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(unit_id, stage, start_id, "complete", flush=True)
