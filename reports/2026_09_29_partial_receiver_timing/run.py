"""Fit an unchanged track likelihood with receiver-specific recording timings."""

import json
import sys
from pathlib import Path

import numpy as np
from partial_timing import PartialTiming
from receiver_filter import receiver_documents
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds789_covariance_position import CovariancePosition  # noqa: E402

unit_id, phase, start = sys.argv[1:]
plan = json.loads((HERE / "plan.json").read_text())
unit = next(u for u in plan["units"] if u["unit_id"] == unit_id)
original = baseline.load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]})
documents = receiver_documents(original, "0") + receiver_documents(original, "1")
n = len(original)
assert n == unit["group"]["size"]
identities = [(d["session_id"], t["track_id"]) for d in documents for t in d["tracks"]]
expected = [(d["session_id"], t["track_id"]) for d in original for t in d["tracks"]]
assert len(set(identities)) == len(identities) and sorted(identities) == sorted(expected)
model = PartialTiming(
    CovariancePosition(documents, plan["config"], 0, baseline.Stationary), n, unit["sigma_s"]
)
parent = HERE / "runs" / unit_id
folder = parent / "fit" / start if phase == "fit" else parent / "held"
validation = None

if phase == "fit":
    initial = np.asarray(next(s["x"] for s in unit["starts"] if s["label"] == start), dtype=float)
    if start == "nested":
        unsplit = CovariancePosition(original, plan["config"], 0, baseline.Stationary)
        old = unsplit.evaluate(initial[: 2 + n], held=True)
        new = model.evaluate(initial, held=True)
        assert new["penalty"] == 0
        score_error = abs(old["score"] - new["score"])
        gradient_error = float(
            np.max(
                abs(
                    old["gradient"]
                    - np.r_[
                        new["gradient"][:2], new["gradient"][2 : 2 + n] + new["gradient"][2 + n :]
                    ]
                )
            )
        )
        assert score_error < 1e-7 and gradient_error < 1e-7

        def key(r):
            return r["session_id"], r["track_id"]

        assert sorted(old["rows"], key=key) == sorted(new["rows"], key=key)
        persisted = json.loads((ROOT / unit["baseline_audit"]).read_text())
        assert abs(old["score"] - persisted["training_log_score"]) < 1e-7
        assert sorted(old["rows"], key=key) == sorted(persisted["rows"], key=key)
        validation = {
            "score_difference": score_error,
            "gradient_difference": gradient_error,
            "held_rows_identical": True,
            "tracks": len(identities),
        }
    bounds = [(-12, 12)] * 2 + [(-5, 5)] * (2 * n)
    fit = minimize(
        model.value_gradient,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 140, "maxfun": 200, "ftol": 1e-14, "gtol": 1e-8, "maxls": 30},
    )
    boundary = any(
        min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    final_evaluation = model.evaluate(fit.x)
    assert abs(final_evaluation["score"] + float(fit.fun)) < 1e-7
    result = {
        "initial": initial.tolist(),
        "x": fit.x.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "raw_training_log_score": final_evaluation["raw_training_log_score"],
        "penalty": final_evaluation["penalty"],
        "evaluations": int(fit.nfev),
        "iterations": int(fit.nit),
        "qualified": bool(fit.success and not boundary and max(abs(fit.jac)) <= 0.01),
        "estimate": dict(
            zip(("latitude_deg", "longitude_deg"), model.coordinates(fit.x), strict=True)
        ),
        "nested_validation": validation,
    }
else:
    selected = json.loads((parent / "selection.json").read_text())["selected"]
    x = np.asarray(selected["x"])
    evaluation = model.evaluate(x, held=True)
    assert abs(evaluation["score"] - selected["training_log_score"]) < 1e-7
    assert abs(evaluation["raw_training_log_score"] - selected["raw_training_log_score"]) < 1e-7
    assert (
        abs(
            sum(r["training_log_score"] for r in evaluation["rows"])
            - evaluation["raw_training_log_score"]
        )
        < 1e-7
    )
    checks = []
    for axis in range(len(x)):
        steps = (1e-3, 5e-4) if axis < 2 else (0.0000625, 0.00003125)
        numeric, tests = [], []
        for step in steps:
            delta = np.eye(len(x))[axis] * step
            finite = (
                model.evaluate(x + delta, gradient=False)["score"]
                - model.evaluate(x - delta, gradient=False)["score"]
            ) / (2 * step)
            crossing = bool(
                axis >= 2 and np.floor((x[axis] - step) / 0.25) != np.floor((x[axis] + step) / 0.25)
            )
            error = abs(finite - evaluation["gradient"][axis])
            numeric.append(finite)
            tests.append(
                {
                    "step": step,
                    "numerical": finite,
                    "absolute_difference": error,
                    "crosses_grid_node": crossing,
                }
            )
        passed = all(
            t["absolute_difference"] < 0.002 and not t["crosses_grid_node"] for t in tests
        ) and (axis < 2 or abs(numeric[0] - numeric[1]) < 0.002)
        checks.append({"axis": axis, "steps": tests, "passed": passed})
    result = {
        "x": x.tolist(),
        "training_log_score": evaluation["score"],
        "raw_training_log_score": evaluation["raw_training_log_score"],
        "penalty": evaluation["penalty"],
        "common_difference_s": evaluation["common_difference_s"],
        "difference_rms_s": evaluation["difference_rms_s"],
        "held_log_score": sum(r["held_log_score"] for r in evaluation["rows"]),
        "rows": evaluation["rows"],
        "gradient": evaluation["gradient"].tolist(),
        "offset_stationarity": evaluation["offset_stationarity"],
        "gradient_checks": checks,
        "audit_passed": all(c["passed"] for c in checks),
    }
result.update(
    unit_id=unit_id, phase=phase, start=start, session_ids=[d["session_id"] for d in documents]
)
with (folder / "result.json").open("x") as f:
    json.dump(result, f, indent=2, allow_nan=False)
print(unit_id, phase, start, "complete", flush=True)
