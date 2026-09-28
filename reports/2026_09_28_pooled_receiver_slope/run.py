"""Fit one pooled arm without reading geographic reference coordinates."""

import json
import math
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_pooled_receiver_slope import PooledReceiverSlope  # noqa: E402

dataset, arm = sys.argv[1:]
assert arm in ("control", "receiver_slope")
row = next(r for r in json.loads((HERE / "plan.json").read_text()) if r["dataset_id"] == dataset)
request = json.loads((ROOT / row["request_path"]).read_text())
response = json.loads((ROOT / row["response_path"]).read_text())
assert response["status"] == "ok" and response["converged"] and not response["boundary_hit"]
assert request["unit"]["session_ids"] == row["session_ids"] and len(request["inputs"]) == 8
documents = baseline.load_documents(request)
model = PooledReceiverSlope(documents, request["config"])
warm = np.array(
    response["diagnostics"]["east_north_km"] + response["diagnostics"]["timing_offsets_s"]
)
point = np.r_[warm, 0.0, 0.0]
historical = model.evaluate(point)
assert math.isclose(
    historical["score"], response["diagnostics"]["train_log_likelihood"], abs_tol=1e-7, rel_tol=0
)
out = HERE / "results" / dataset / arm
with (out / "historical.json").open("x") as f:
    json.dump(
        {
            "x": warm.tolist(),
            "training_log_score": historical["score"],
            "gradient": historical["gradient"].tolist(),
            "estimate": response["estimate"],
        },
        f,
        indent=2,
    )
free = arm == "receiver_slope"
bounds = [(-12, 12)] * 2 + [(-5, 5)] * 8 + ([(-20, 20)] * 2 if free else [])


def objective(x):
    result = model.evaluate(x if free else np.r_[x, 0.0, 0.0])
    return -result["score"], -result["gradient"][: len(x)]


runs = []
for delta in (0.0, -0.25, 0.25):
    start = warm.copy()
    start[2:] = np.clip(start[2:] + delta, -5, 5)
    if free:
        start = np.r_[start, 0.0, 0.0]
    fit = minimize(
        objective,
        start,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 100, "maxfun": 180, "ftol": 1e-10, "gtol": 1e-5, "maxls": 30},
    )
    boundary = any(
        min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    run = {
        "timing_start_delta_s": delta,
        "start": start.tolist(),
        "x": fit.x.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "evaluations": int(fit.nfev),
        "iterations": int(fit.nit),
        "qualified": bool(fit.success and not boundary and np.max(np.abs(fit.jac)) <= 0.01),
    }
    runs.append(run)
    with (out / "starts.jsonl").open("a") as f:
        f.write(json.dumps(run) + "\n")
    print(json.dumps({"dataset_id": dataset, "arm": arm, **run}), flush=True)
successful = [r for r in runs if r["success"]]
selected = max(successful, key=lambda r: r["training_log_score"]) if successful else None
result = {
    "dataset_id": dataset,
    "arm": arm,
    "starts": runs,
    "selected": selected,
    "runtime": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__},
}
if selected:
    point = np.array(selected["x"] if free else selected["x"] + [0.0, 0.0])
    held = model.held(point)
    assert math.isclose(
        sum(r["training_log_score"] for r in held),
        selected["training_log_score"],
        abs_tol=1e-7,
        rel_tol=0,
    )
    lat, lon = model.coordinates(point)
    result.update(
        estimate={"latitude_deg": lat, "longitude_deg": lon},
        evaluation=held,
        held_log_score=sum(r["held_log_score"] for r in held),
    )
with (out / "result.json").open("x") as f:
    json.dump(result, f, indent=2, allow_nan=False)
