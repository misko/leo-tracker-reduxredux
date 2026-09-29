"""Shared position and transfer on timestamp-selected temporal panels."""

import json
import sys
from pathlib import Path

import numpy as np
from receiver_filter import receiver_documents
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds789_covariance_position import CovariancePosition  # noqa: E402

decay, unit_id, stage, start_id = sys.argv[1:]
decay = int(decay)
plan = json.loads((HERE / "plan.json").read_text())
spec = next(m for m in plan["models"] if m["decay_s"] == decay)
unit = next(u for u in spec["units"] if u["unit_id"] == unit_id)
target = stage.startswith("target")
groups = [
    g
    for g in spec["groups"]
    if (
        g["dataset_id"] == unit["excluded_dataset"]
        if target
        else g["dataset_id"] in unit["source_datasets"]
    )
]
all_documents = baseline.load_documents(
    {"config": plan["config"], "inputs": [i for g in groups for i in g["inputs"]]}
)
assert len(groups) == 1 and not target
receiver = groups[0]["receiver_id"]
documents = receiver_documents(all_documents, receiver)
assert [
    {"session_id": d["session_id"], "track_ids": [t["track_id"] for t in d["tracks"]]}
    for d in documents
] == groups[0]["receiver_partition"]
assert [d["session_id"] for d in documents] == [s for g in groups for s in g["session_ids"]]
model = CovariancePosition(documents, plan["config"], decay, baseline.Stationary)
parent = HERE / f"t{decay}" / unit_id
folder = parent / stage / start_id if stage.endswith("fit") else parent / stage

if stage.endswith("fit"):
    if target:
        donor = json.loads((parent / "source-selection.json").read_text())["selected"]
        position = np.asarray(donor["x"][:2])
        initial = np.full(len(documents), float(start_id))
        bounds = [(-5, 5)] * len(documents)

        def objective(x):
            value, gradient = model.value_gradient(np.r_[position, x])
            return value, gradient[2:]
    else:
        initial = np.asarray(
            next(s["x"] for s in unit["starts"] if s["source_dataset"] == start_id)
        )
        bounds = [(-12, 12)] * 2 + [(-5, 5)] * len(documents)
        objective = model.value_gradient
    fit = minimize(
        objective,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={
            "maxiter": 140,
            "maxfun": 200,
            "ftol": 1e-14,
            "gtol": 1e-8,
            "maxls": 30,
        },
    )
    x = np.r_[position, fit.x] if target else fit.x
    boundary = any(
        min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    result = {
        "initial": initial.tolist(),
        "x": x.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "evaluations": int(fit.nfev),
        "iterations": int(fit.nit),
        "qualified": bool(fit.success and not boundary and max(abs(fit.jac)) <= 0.01),
        "estimate": dict(zip(("latitude_deg", "longitude_deg"), model.coordinates(x), strict=True)),
    }
else:
    selected = json.loads(
        (parent / ("target-selection.json" if target else "source-selection.json")).read_text()
    )["selected"]
    x = np.asarray(selected["x"])
    evaluation = model.evaluate(x, gradient=True, held=True)
    assert abs(evaluation["score"] - selected["training_log_score"]) < 1e-7
    audit = []
    if not target:
        for step in (1e-3, 5e-4):
            for axis in (0, 1):
                delta = np.eye(len(x))[axis] * step
                finite = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / (2 * step)
                error = abs(finite - evaluation["gradient"][axis])
                assert error < 0.002, error
                audit.append(
                    {
                        "axis": axis,
                        "step_km": step,
                        "numerical": finite,
                        "analytic": float(evaluation["gradient"][axis]),
                        "absolute_difference": error,
                    }
                )
    result = {
        "training_log_score": evaluation["score"],
        "held_log_score": sum(r["held_log_score"] for r in evaluation["rows"]),
        "rows": evaluation["rows"],
        "offset_stationarity": evaluation["offset_stationarity"],
        "full_training_gradient": evaluation["gradient"].tolist(),
        "position_gradient_check": audit,
    }
    other_receiver = "1" if receiver == "0" else "0"
    other_documents = receiver_documents(all_documents, other_receiver)
    other_model = CovariancePosition(other_documents, plan["config"], decay, baseline.Stationary)
    other = other_model.evaluate(x, gradient=False, held=True)
    result["other_receiver"] = {
        "receiver_id": other_receiver,
        "training_log_score": other["score"],
        "held_log_score": sum(r["held_log_score"] for r in other["rows"]),
        "rows": other["rows"],
        "offset_stationarity": other["offset_stationarity"],
        "position_and_timings": x.tolist(),
    }
result.update(
    decay_s=decay,
    unit_id=unit_id,
    stage=stage,
    start_id=start_id,
    session_ids=[d["session_id"] for d in documents],
    receiver_id=receiver,
)
with (folder / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(decay, unit_id, stage, start_id, "complete", flush=True)
