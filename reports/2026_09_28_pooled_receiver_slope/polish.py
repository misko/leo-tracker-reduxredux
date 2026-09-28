"""One deterministic numerical refinement, preserving the original comparison."""

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_pooled_receiver_slope import PooledReceiverSlope  # noqa: E402

dataset, arm = sys.argv[1:]
out = HERE / "polished" / dataset / arm
path = HERE / "results" / dataset / arm / "result.json"
if not path.exists():
    (out / "result.json").write_text(
        json.dumps({"dataset_id": dataset, "arm": arm, "state": "missing_original_result"})
    )
    raise SystemExit(0)
original = json.loads(path.read_text())
selected = original["selected"]
if selected is None or not selected["success"] or selected["boundary_hit"]:
    (out / "result.json").write_text(
        json.dumps({"dataset_id": dataset, "arm": arm, "state": "ineligible_original_result"})
    )
    raise SystemExit(0)
row = next(r for r in json.loads((HERE / "plan.json").read_text()) if r["dataset_id"] == dataset)
request = json.loads((ROOT / row["request_path"]).read_text())
model = PooledReceiverSlope(baseline.load_documents(request), request["config"])
free = arm == "receiver_slope"


def objective(x):
    value = model.evaluate(x if free else np.r_[x, 0.0, 0.0])
    return -value["score"], -value["gradient"][: len(x)]


bounds = [(-12, 12)] * 2 + [(-5, 5)] * 8 + ([(-20, 20)] * 2 if free else [])
start = np.array(selected["x"])
fit = minimize(
    objective,
    start,
    jac=True,
    method="L-BFGS-B",
    bounds=bounds,
    options={"maxiter": 40, "maxfun": 60, "ftol": 1e-13, "gtol": 1e-6, "maxls": 30},
)
boundary = any(min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True))
nondecreasing = -float(fit.fun) >= selected["training_log_score"] - 1e-7
point = fit.x if free else np.r_[fit.x, 0.0, 0.0]
held = model.held(point)
assert math.isclose(
    sum(r["training_log_score"] for r in held), -float(fit.fun), abs_tol=1e-7, rel_tol=0
)
lat, lon = model.coordinates(point)
result = {
    "dataset_id": dataset,
    "arm": arm,
    "state": "returned",
    "x": fit.x.tolist(),
    "success": bool(fit.success),
    "message": str(fit.message),
    "boundary_hit": boundary,
    "gradient": (-fit.jac).tolist(),
    "training_log_score": -float(fit.fun),
    "evaluations": int(fit.nfev),
    "iterations": int(fit.nit),
    "training_nondecreasing": nondecreasing,
    "qualified": bool(
        fit.success and not boundary and np.max(np.abs(fit.jac)) <= 0.01 and nondecreasing
    ),
    "original_qualified": selected["qualified"],
    "original_x": selected["x"],
    "position_displacement_m": float(np.linalg.norm(fit.x[:2] - start[:2]) * 1000),
    "estimate": {"latitude_deg": lat, "longitude_deg": lon},
    "evaluation": held,
    "held_log_score": sum(r["held_log_score"] for r in held),
}
with (out / "result.json").open("x") as f:
    json.dump(result, f, indent=2, allow_nan=False)
print(json.dumps({k: v for k, v in result.items() if k != "evaluation"}, indent=2))
