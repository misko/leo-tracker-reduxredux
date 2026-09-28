"""Fixed likelihoods and generic starts on validated temporal panels."""

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds789_covariance_position import CovariancePosition  # noqa: E402

dataset, family, stage = sys.argv[1:]
request = json.loads((HERE / dataset / "request.json").read_text())
documents = baseline.load_documents(request)
baseline.baseline.profile = baseline.profile
model = (
    baseline.JointObjective(documents, request["config"])
    if family == "iid"
    else CovariancePosition(
        documents, request["config"], 0 if family == "shared" else 10, baseline.Stationary
    )
)
parent = HERE / dataset / family
folder = parent / stage
if stage.startswith("fit"):
    position = {"fit0": [0.0, 0.0], "fit1": [3.0, -3.0], "fit2": [-3.0, 3.0]}[stage]
    initial = np.r_[position, np.zeros(len(documents))]
    bounds = [(-12, 12)] * 2 + [(-5, 5)] * len(documents)
    fit = minimize(
        model.value_gradient,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 140, "maxfun": 200, "ftol": 1e-14, "gtol": 1e-8, "maxls": 30},
    )
    boundary = any(
        min(abs(v - a), abs(v - b)) < 0.001 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    result = {
        "x": fit.x.tolist(),
        "initial": initial.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "evaluations": int(fit.nfev),
        "iterations": int(fit.nit),
        "qualified": bool(fit.success and not boundary and max(abs(fit.jac)) <= 0.01),
        "estimate": dict(
            zip(("latitude_deg", "longitude_deg"), model.coordinates(fit.x), strict=True)
        ),
    }
else:
    selected = json.loads((parent / "selection.json").read_text())["selected"]
    x = np.asarray(selected["x"])
    value, gradient = model.value_gradient(x)
    assert abs(-value - selected["training_log_score"]) < 1e-7
    audit = []
    for step in (1e-3, 5e-4):
        for axis in (0, 1):
            delta = np.eye(len(x))[axis] * step
            finite = (model.value_gradient(x + delta)[0] - model.value_gradient(x - delta)[0]) / (
                2 * step
            )
            difference = abs(finite - gradient[axis])
            assert difference < 0.002, difference
            audit.append(
                {
                    "axis": axis,
                    "step_km": step,
                    "analytic_loss_gradient": float(gradient[axis]),
                    "numerical_loss_gradient": float(finite),
                    "absolute_difference": difference,
                }
            )
    if family != "iid":
        evaluation = model.evaluate(x, gradient=False, held=True)
        rows = evaluation["rows"]
    else:
        rows = []
        for di, (doc, local_model) in enumerate(zip(documents, model.models, strict=True)):
            point = np.r_[x[:2], x[di + 2]]
            for track in doc["tracks"]:
                prediction, visible = local_model.prediction(track, point)
                train, joint, audits, offsets = baseline.profile(
                    track["y"][None, :] - prediction, track["mask"]
                )
                assert all(a["converged"] for a in audits)
                train = np.where(visible, train, -np.inf)
                joint = np.where(visible, joint, -np.inf)
                normal = float(logsumexp(train))
                rows.append(
                    {
                        "session_id": doc["session_id"],
                        "track_id": track["track_id"],
                        "training_log_score": normal - math.log(track["catalogue_size"]),
                        "held_log_score": float(logsumexp(joint)) - normal,
                        "weights": np.exp(train - normal).tolist(),
                        "offsets": offsets.tolist(),
                        "held_observations": int((~track["mask"]).sum()),
                    }
                )
    assert abs(sum(r["training_log_score"] for r in rows) + value) < 1e-7
    result = {
        "training_log_score": -float(value),
        "held_log_score": sum(r["held_log_score"] for r in rows),
        "rows": rows,
        "gradient_check": audit,
    }
result.update(dataset=dataset, family=family, stage=stage)
with (folder / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(dataset, family, stage, "complete", flush=True)
