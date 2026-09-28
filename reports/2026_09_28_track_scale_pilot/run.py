"""Run a frozen scale pilot without loading any reference position."""

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
from ds7_shared_slope_shadow import prepare  # noqa: E402
from ds7_track_scale_mixture import evaluate  # noqa: E402

unit = sys.argv[1]
row = next(r for r in json.loads((HERE / "plan.json").read_text()) if r["unit_id"] == unit)
out = HERE / "results" / unit
request = json.loads((ROOT / row["request_path"]).read_text())
response = json.loads((ROOT / row["response_path"]).read_text())
document = baseline.load_documents(request)[0]
assert len(request["inputs"]) == 1
assert document["session_id"] == row["session_id"]
model = baseline.Stationary(document, request["config"])
x = np.array(response["diagnostics"]["east_north_km"] + response["diagnostics"]["timing_offsets_s"])
historical = evaluate(
    document["tracks"], model.prediction, x, gradient=True, held=True, scales=(100,), priors=(1,)
)
reference = prepare(document, request["config"], x).evaluate(0, held=True)
assert math.isclose(
    historical["training_log_score"],
    response["diagnostics"]["train_log_likelihood"],
    abs_tol=1e-8,
    rel_tol=0,
)
assert math.isclose(
    historical["held_log_score"], reference["held_log_score"], abs_tol=1e-8, rel_tol=0
)
with (out / "baseline.json").open("x") as f:
    json.dump(
        {
            "unit_id": unit,
            "estimate": response["estimate"],
            "x": x.tolist(),
            "original_qualified": response["converged"] and not response["boundary_hit"],
            "gradient_screen": max(abs(v) for v in historical["gradient"]) <= 0.01,
            "evaluation": historical,
        },
        f,
        indent=2,
    )

for arm, scales, priors in (("mixture", (100, 1000), (0.9, 0.1)), ("broad_only", (1000,), (1,))):
    runs = []

    def objective(point, scales=scales, priors=priors):
        value = evaluate(
            document["tracks"], model.prediction, point, gradient=True, scales=scales, priors=priors
        )
        return -value["training_log_score"], -np.asarray(value["gradient"])

    bounds = [(-12, 12), (-12, 12), (-5, 5)]
    for tau in (0.0, -2.0, 2.0):
        fit = minimize(
            objective,
            np.array([0.0, 0.0, tau]),
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 100, "maxfun": 180, "ftol": 1e-10, "gtol": 1e-5, "maxls": 30},
        )
        boundary = any(
            min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
        )
        run = {
            "timing_start_s": tau,
            "x": fit.x.tolist(),
            "success": bool(fit.success),
            "message": str(fit.message),
            "boundary_hit": boundary,
            "gradient": (-fit.jac).tolist(),
            "training_log_score": -float(fit.fun),
            "qualified": bool(fit.success and not boundary and np.max(np.abs(fit.jac)) <= 0.01),
            "evaluations": int(fit.nfev),
            "iterations": int(fit.nit),
        }
        runs.append(run)
        with (out / (arm + "-starts.jsonl")).open("a") as f:
            f.write(json.dumps(run) + "\n")
        print(json.dumps({"unit_id": unit, "arm": arm, **run}), flush=True)
    good = [r for r in runs if r["success"]]
    selected = max(good, key=lambda r: r["training_log_score"]) if good else None
    result = {
        "unit_id": unit,
        "arm": arm,
        "scales_hz": scales,
        "priors": priors,
        "starts": runs,
        "selected": selected,
    }
    if selected:
        point = np.asarray(selected["x"])
        result["evaluation"] = evaluate(
            document["tracks"],
            model.prediction,
            point,
            gradient=True,
            held=True,
            scales=scales,
            priors=priors,
        )
        assert math.isclose(
            result["evaluation"]["training_log_score"],
            selected["training_log_score"],
            abs_tol=1e-8,
            rel_tol=0,
        )
        lat, lon = model.coordinates(point)
        result["estimate"] = {"latitude_deg": lat, "longitude_deg": lon}
    with (out / (arm + ".json")).open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
