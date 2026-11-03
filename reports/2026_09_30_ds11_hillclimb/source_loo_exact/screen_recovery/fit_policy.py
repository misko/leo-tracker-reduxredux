"""Uniform L-BFGS-B then narrowly gated SLSQP fit policy."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


precision = _module("screen_recovery_precision", EXPERIMENT / "precision" / "run.py")
solver = _module("screen_recovery_solver", EXPERIMENT / "recovery" / "solver.py")


def _attempt(solver_name, result, qualification, **extra):
    row = {
        "solver": solver_name,
        "success": bool(result.success),
        "qualified": bool(qualification["qualified"]),
        "message": str(result.message),
        "x": np.asarray(result.x, dtype=float).tolist(),
        "objective": float(result.fun),
        "gradient": np.asarray(result.jac, dtype=float).tolist(),
        "qualification": dict(qualification),
    }
    for name in ("nfev", "nit"):
        if hasattr(result, name):
            row[name] = int(getattr(result, name))
    row.update(extra)
    return row


def _precision_gate(model, result, bounds):
    x = np.asarray(result.x, dtype=float)
    gradient = np.asarray(model.evaluate(x, gradient=True)["gradient"], dtype=float)
    primary = precision.hessian_summary(
        precision.negative_hessian(model, x, precision.STEPS)
    )
    half = precision.hessian_summary(
        precision.negative_hessian(model, x, precision.STEPS / 2.0)
    )
    primary_symmetric = np.asarray(primary["symmetric"], dtype=float)
    half_symmetric = np.asarray(half["symmetric"], dtype=float)
    disagreement = float(
        np.linalg.norm(primary_symmetric - half_symmetric)
        / max(np.linalg.norm(half_symmetric), np.finfo(float).tiny)
    )
    primary_condition = primary["condition_number"]
    half_condition = half["condition_number"]
    delta = np.linalg.solve(primary_symmetric, gradient)
    en_m = float(1000.0 * np.linalg.norm(delta[:2]))
    tau_s = float(delta[2])
    finite = bool(
        np.isfinite(gradient).all()
        and np.isfinite(primary_symmetric).all()
        and np.isfinite(half_symmetric).all()
        and np.isfinite(delta).all()
        and np.isfinite(disagreement)
        and primary_condition is not None
        and half_condition is not None
    )
    passed = bool(
        finite
        and primary["positive_definite"]
        and half["positive_definite"]
        and primary["relative_asymmetry"] <= 0.005
        and half["relative_asymmetry"] <= 0.005
        and disagreement <= 0.005
        and primary_condition <= 1e10
        and half_condition <= 1e10
        and en_m <= 0.01
        and abs(tau_s) <= 1e-5
    )
    return {
        "passed": passed,
        "finite": finite,
        "original_positive_definite": primary["positive_definite"],
        "half_positive_definite": half["positive_definite"],
        "original_relative_asymmetry": primary["relative_asymmetry"],
        "half_relative_asymmetry": half["relative_asymmetry"],
        "step_halving_relative_disagreement": disagreement,
        "original_condition_number": primary_condition,
        "half_condition_number": half_condition,
        "newton_displacement": delta.tolist(),
        "newton_en_displacement_m": en_m,
        "newton_time_displacement_s": tau_s,
        "limits": {
            "relative_asymmetry": 0.005,
            "step_halving_relative_disagreement": 0.005,
            "condition_number": 1e10,
            "newton_en_displacement_m": 0.01,
            "absolute_newton_time_displacement_s": 1e-5,
        },
    }


def fit_policy(model, seed, bounds, pilot, exact):
    """Run the original fit first and at most one gated SLSQP continuation."""
    original, qualification = pilot.fit_local(
        model, seed, bounds, exact.qualify
    )
    records = [_attempt("L-BFGS-B", original, qualification)]
    if qualification["qualified"]:
        records[0]["returned"] = True
        return original, qualification, records

    try:
        near_stationary = solver.eligible(original, qualification, bounds)
    except Exception as exc:  # preserve the original failed fit
        records.append({
            "solver": "SLSQP",
            "attempted": False,
            "accepted": False,
            "failure": f"{type(exc).__name__}: {exc}",
        })
        records[0]["returned"] = True
        return original, qualification, records
    if not near_stationary:
        records.append({
            "solver": "SLSQP",
            "attempted": False,
            "accepted": False,
            "gate": {"eligible_failed_fit": False, "passed": False},
        })
        records[0]["returned"] = True
        return original, qualification, records

    try:
        gate = _precision_gate(model, original, bounds)
    except Exception as exc:  # preserve the original failed fit
        records.append({
            "solver": "SLSQP",
            "attempted": False,
            "accepted": False,
            "gate": {"eligible_failed_fit": True, "passed": False},
            "failure": f"{type(exc).__name__}: {exc}",
        })
        records[0]["returned"] = True
        return original, qualification, records
    gate = {"eligible_failed_fit": True, **gate}
    if not gate["passed"]:
        records.append({
            "solver": "SLSQP", "attempted": False, "accepted": False,
            "gate": gate,
        })
        records[0]["returned"] = True
        return original, qualification, records

    try:
        recovered, recovered_qualification, accepted = solver.recover(
            model, original, qualification, bounds, exact.qualify
        )
        records.append(_attempt(
            "SLSQP", recovered, recovered_qualification,
            attempted=True, accepted=bool(accepted), gate=gate,
        ))
    except Exception as exc:  # preserve the original failed fit
        records.append({
            "solver": "SLSQP",
            "attempted": True,
            "accepted": False,
            "gate": gate,
            "failure": f"{type(exc).__name__}: {exc}",
        })
        records[0]["returned"] = True
        return original, qualification, records
    if accepted:
        records[0]["returned"] = False
        records[1]["returned"] = True
        return recovered, recovered_qualification, records
    records[0]["returned"] = True
    records[1]["returned"] = False
    return original, qualification, records
