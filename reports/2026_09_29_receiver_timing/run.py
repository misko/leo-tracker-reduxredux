"""Refit target timings while holding each source-receiver position fixed."""

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

unit_id, stage, start = sys.argv[1:]
plan = json.loads((HERE / "plan.json").read_text())
unit = next(u for u in plan["units"] if u["unit_id"] == unit_id)
documents = receiver_documents(
    baseline.load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]}),
    unit["target_receiver"],
)
assert [
    {"session_id": d["session_id"], "track_ids": [t["track_id"] for t in d["tracks"]]}
    for d in documents
] == unit["group"]["receiver_partition"]
model = CovariancePosition(documents, plan["config"], 0, baseline.Stationary)
position = np.asarray(unit["position"])
parent = HERE / "runs" / unit_id
folder = parent / "fit" / start if stage == "fit" else parent / "held"


def objective(timings):
    value, gradient = model.value_gradient(np.r_[position, timings])
    return value, gradient[2:]


if stage == "fit":
    initial = np.asarray(next(s["timings"] for s in unit["starts"] if s["label"] == start))
    fit = minimize(
        objective,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=[(-5, 5)] * len(documents),
        options={"maxiter": 140, "maxfun": 200, "ftol": 1e-14, "gtol": 1e-8, "maxls": 30},
    )
    boundary = bool(np.any(np.abs(fit.x) > 4.999))
    result = {
        "initial": initial.tolist(),
        "timings": fit.x.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "iterations": int(fit.nit),
        "evaluations": int(fit.nfev),
        "qualified": bool(fit.success and not boundary and np.max(np.abs(fit.jac)) <= 0.01),
    }
else:
    assert stage == "held"
    selected = json.loads((parent / "selection.json").read_text())["selected"]
    x = np.r_[position, selected["timings"]]
    evaluation = model.evaluate(x, gradient=True, held=True)
    assert abs(evaluation["score"] - selected["training_log_score"]) < 1e-7
    checks = []
    for step in (0.001, 0.0005):
        for index in range(2, len(x)):
            delta = np.eye(len(x))[index] * step
            numerical = (
                model.evaluate(x + delta, gradient=False)["score"]
                - model.evaluate(x - delta, gradient=False)["score"]
            ) / (2 * step)
            error = abs(numerical - evaluation["gradient"][index])
            assert error < 0.002, error
            checks.append({"timing_index": index - 2, "step_s": step, "absolute_difference": error})
    result = {
        "training_log_score": evaluation["score"],
        "held_log_score": sum(r["held_log_score"] for r in evaluation["rows"]),
        "timings": selected["timings"],
        "rows": evaluation["rows"],
        "full_gradient": evaluation["gradient"].tolist(),
        "timing_gradient_checks": checks,
        "offset_stationarity": evaluation["offset_stationarity"],
    }
result.update(
    unit_id=unit_id,
    stage=stage,
    start=start,
    position=position.tolist(),
    target_receiver=unit["target_receiver"],
    session_ids=[d["session_id"] for d in documents],
)
assert result["position"] == unit["position"]
with (folder / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(unit_id, stage, start, "complete", flush=True)
