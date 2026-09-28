"""Bounded covariance preflight, geographic fit and selected-point audit."""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds789_covariance_position import CovariancePosition  # noqa: E402

dataset, decay, stage = sys.argv[1:]
decay = int(decay)
folder = HERE / dataset / f"t{decay}" / stage
plan = json.loads((HERE.parent / "2026_09_28_cross_dataset_position/plan.json").read_text())
group = next(g for g in plan["groups"] if g["dataset_id"] == dataset)
original = json.loads((ROOT / group["source_point_path"]).read_text())
documents = baseline.load_documents({"config": plan["config"], "inputs": group["inputs"]})
model = CovariancePosition(documents, plan["config"], decay, baseline.Stationary)
point = np.asarray(original["x"])
bounds = [(-12, 12)] * 2 + [(-5, 5)] * len(documents)


def check(x, axes):
    result = model.evaluate(x)
    numerical = []
    for axis in axes:
        step = 1e-3 if axis < 2 else 1e-4
        delta = np.eye(len(x))[axis] * step
        plus = model.evaluate(x + delta, gradient=False)["score"]
        minus = model.evaluate(x - delta, gradient=False)["score"]
        numerical.append((plus - minus) / (2 * step))
    error = float(np.max(abs(np.asarray(numerical) - result["gradient"][axes])))
    assert error < 0.002, (axes, numerical, result["gradient"].tolist(), error)
    return {
        "axes": axes,
        "numerical": numerical,
        "analytic": result["gradient"][axes].tolist(),
        "maximum_difference": error,
    }


if stage == "preflight":
    audit = check(point, [0, 1, 2])
    initial = model.evaluate(point, gradient=False, held=True)
    shadow = json.loads(
        (HERE.parent / f"2026_09_28_correlated_residual_shadow/{dataset}/result.json").read_text()
    )
    old = next(a for a in shadow["arms"] if a["id"] == f"mvt_s100_t{decay}")
    assert initial["score"] >= old["train"] - 1e-7
    result = {
        "gradient_check": audit,
        "initial_training_score": initial["score"],
        "initial_held_score": sum(r["held_log_score"] for r in initial["rows"]),
        "initial_rows": initial["rows"],
        "offset_stationarity": initial["offset_stationarity"],
        "training_gain_from_offset_refit": initial["score"] - old["train"],
    }
elif stage.startswith("fit_"):
    initial = point if stage == "fit_original" else np.zeros_like(point)
    fit = minimize(
        model.value_gradient,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 120, "maxfun": 180, "ftol": 1e-12, "gtol": 1e-6, "maxls": 30},
    )
    boundary = any(
        min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    result = {
        "x": fit.x.tolist(),
        "initial": initial.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "qualified": bool(fit.success and not boundary and max(abs(fit.jac)) <= 0.01),
        "evaluations": int(fit.nfev),
        "iterations": int(fit.nit),
        "estimate": dict(
            zip(("latitude_deg", "longitude_deg"), model.coordinates(fit.x), strict=True)
        ),
    }
elif stage == "diagnostic":
    selected = json.loads((folder.parent / "selection.json").read_text())["selected"]
    point = np.asarray(selected["x"])
    audit = check(point, list(range(len(point))))
    evaluation = model.evaluate(point, gradient=False, held=True)
    assert abs(evaluation["score"] - selected["training_log_score"]) < 1e-7
    hessian = np.empty((len(point), len(point)))
    for axis in range(len(point)):
        delta = np.eye(len(point))[axis] * (1e-3 if axis < 2 else 1e-4)
        gp = model.value_gradient(point + delta)[1]
        gm = model.value_gradient(point - delta)[1]
        hessian[:, axis] = (gp - gm) / (2 * delta[axis])
    asymmetry = float(abs(hessian - hessian.T).max())
    symmetric = (hessian + hessian.T) / 2
    nuisance_eigenvalues = np.linalg.eigvalsh(symmetric[2:, 2:])
    positional = None
    if min(nuisance_eigenvalues) > 0:
        positional = symmetric[:2, :2] - symmetric[:2, 2:] @ np.linalg.solve(
            symmetric[2:, 2:], symmetric[2:, :2]
        )
    result = {
        "gradient_check": audit,
        "training_log_score": evaluation["score"],
        "held_log_score": sum(r["held_log_score"] for r in evaluation["rows"]),
        "rows": evaluation["rows"],
        "offset_stationarity": evaluation["offset_stationarity"],
        "hessian": hessian.tolist(),
        "hessian_asymmetry": asymmetry,
        "nuisance_eigenvalues": nuisance_eigenvalues.tolist(),
        "profiled_position_information": None if positional is None else positional.tolist(),
        "profiled_position_eigenvalues": None
        if positional is None
        else np.linalg.eigvalsh(positional).tolist(),
    }
else:
    raise ValueError(stage)
result.update(dataset=dataset, decay_s=decay, stage=stage)
with (folder / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(dataset, decay, stage, "complete", flush=True)
