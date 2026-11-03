"""Bounded curvature and finite-difference audit of one saved failed endpoint."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

import numpy as np


HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
SCREEN = EXPERIMENT / "screen"
RESTART = EXPERIMENT / "restart"
KEY = "04_robust_t8_scale100_65855"
STEPS = np.asarray((1e-4, 1e-4, 1e-5), dtype=float)
BOUNDS = np.asarray(((-12.0, 12.0), (-12.0, 12.0), (-5.0, 5.0)), dtype=float)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def check_sources(record):
    for path, expected in record["sources"].items():
        if digest(path) != expected:
            raise ValueError(f"changed source: {path}")


def load_case():
    """Return the exact retained model, authoritative record, context, and sources."""
    runner = load_module("precision_screen", SCREEN / "run.py")
    plan = runner.load_plan()
    job = next(job for job in plan["jobs"] if runner.job_key(job) == KEY)
    if job["cache"] is not None:
        raise ValueError("precision target unexpectedly became cached")

    result_path = SCREEN / "runs" / f"{KEY}.json"
    receipt_path = result_path.with_suffix(".receipt.json")
    old = json.loads(result_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if (
        old.get("schema") != "ds11-source-loo-exact-screen-fold/v1"
        or old.get("job_key") != KEY
        or old.get("index") != 4
        or old.get("family") != "robust_t8_scale100"
        or old.get("norad") != 65855
        or old.get("reference_used") is not False
        or old.get("full_endpoint_x") != job["full_endpoint_x"]
        or receipt.get("job_key") != KEY
        or receipt.get("index") != 4
        or receipt.get("family") != "robust_t8_scale100"
        or receipt.get("norad") != 65855
        or receipt.get("exit_code") != 0
        or receipt.get("run_sha256") != digest(SCREEN / "run.py")
        or receipt.get("plan_sha256") != digest(SCREEN / "plan.json")
        or receipt.get("protocol_sha256") != digest(SCREEN / "PROTOCOL.md")
    ):
        raise ValueError("authoritative failed result or receipt binding mismatch")
    check_sources(old)
    fold = old["fold"]
    optimizer = fold["optimizer"]
    if (
        optimizer.get("success") is not False
        or optimizer.get("qualified") is not False
        or optimizer.get("boundary") is not False
        or not np.isfinite(fold["x"]).all()
        or not math.isfinite(fold["retained_score"])
    ):
        raise ValueError("authoritative fold is not the finite unsuccessful target")

    restart_path = RESTART / "result.json"
    restart_receipt_path = RESTART / "receipt.json"
    restart = json.loads(restart_path.read_text())
    restart_receipt = json.loads(restart_receipt_path.read_text())
    check_sources(restart)
    if (
        restart_receipt.get("exit_code") != 0
        or restart.get("job_key") != KEY
        or restart.get("x") != fold["x"]
        or restart.get("retained_score") != fold["retained_score"]
        or restart.get("common_held_score") != fold["common_held_score"]
        or restart.get("optimizer", {}).get("success") is not False
    ):
        raise ValueError("restart result does not reproduce the saved failure")

    pilot = runner.module("precision_pilot", EXPERIMENT / "run.py")
    pilot.fast.baseline.profile = pilot.fast.profile
    diagnose = runner.module("precision_diagnose", pilot.HILL / "source_loo" / "diagnose.py")
    context_module = runner.module("precision_context", SCREEN / "input_context.py")
    source = runner.module("precision_source", pilot.HILL / "source_balance" / "model.py")
    robust = runner.module("precision_robust", pilot.HILL / "robust" / "model.py")
    _, base, entry, documents, _, norad_map = context_module.load_scan(4)
    if old["session_id"] != entry["session_id"]:
        raise ValueError("saved result session changed")
    iid_family = diagnose.FAMILIES["iid_t4_scale100"]
    _, _, _, iid_x, _, _ = diagnose.load_endpoint(
        "iid_t4_scale100", iid_family, 4, entry["session_id"]
    )
    assignments = source.freeze_assignments(documents, base["config"], iid_x, norad_map)
    weights = source.derive_weights(assignments, "source_receiver_equal")
    runner.check_frozen_assignments(plan, 4, assignments, weights)
    subset = pilot.retained_fold(assignments, weights, job["norad"])
    ids = [assignments[i]["track_id"] for i in subset["omitted_indices"]]
    if ids != job["source_track_ids"] or ids != fold["track_ids"]:
        raise ValueError("target omitted membership changed")
    retained = diagnose.subset_document(documents[0], subset["retained_indices"])
    model = diagnose.build_evaluator(
        "robust", "df8", retained, base["config"],
        {"source": source, "robust": robust},
    )
    initial = model.evaluate(np.asarray(fold["x"], dtype=float), gradient=True)
    if (
        abs(initial["score"] - fold["retained_score"]) > 1e-7
        or abs(np.max(np.abs(initial["gradient"])) - optimizer["gradient_max_abs"]) > 1e-7
    ):
        raise ValueError("reconstructed target does not replay saved score/gradient")

    sources = {
        **plan["sources"],
        str(SCREEN / "plan.json"): digest(SCREEN / "plan.json"),
        str(result_path): digest(result_path),
        str(receipt_path): digest(receipt_path),
        str(restart_path): digest(restart_path),
        str(restart_receipt_path): digest(restart_receipt_path),
        str(HERE / "run.py"): digest(HERE / "run.py"),
        str(HERE / "PROTOCOL.md"): digest(HERE / "PROTOCOL.md"),
        str(HERE / "test_run.py"): digest(HERE / "test_run.py"),
    }
    context = {
        "plan": plan,
        "job": job,
        "config": base["config"],
        "documents": documents,
        "subset": subset,
        "bounds": BOUNDS.copy(),
        "initial": initial,
    }
    return model, old, context, sources


def negative_hessian(model, x, steps):
    """Central analytic-gradient estimate of the observed negative Hessian."""
    x = np.asarray(x, dtype=float)
    steps = np.asarray(steps, dtype=float)
    if x.shape != (3,) or steps.shape != (3,) or np.any(steps <= 0):
        raise ValueError("x and positive steps must each have length three")
    matrix = np.empty((3, 3), dtype=float)
    for axis, step in enumerate(steps):
        delta = np.zeros(3)
        delta[axis] = step
        plus = np.asarray(model.evaluate(x + delta, gradient=True)["gradient"], dtype=float)
        minus = np.asarray(model.evaluate(x - delta, gradient=True)["gradient"], dtype=float)
        matrix[:, axis] = -(plus - minus) / (2.0 * step)
    return matrix


def hessian_summary(matrix):
    matrix = np.asarray(matrix, dtype=float)
    symmetric = 0.5 * (matrix + matrix.T)
    eigenvalues = np.linalg.eigvalsh(symmetric)
    norm = max(float(np.linalg.norm(matrix)), float(np.finfo(float).tiny))
    condition = float(np.linalg.cond(symmetric))
    return {
        "raw": matrix.tolist(),
        "symmetric": symmetric.tolist(),
        "relative_asymmetry": float(np.linalg.norm(matrix - matrix.T) / norm),
        "eigenvalues": eigenvalues.tolist(),
        "positive_definite": bool(np.all(eigenvalues > 0.0)),
        "condition_number": condition if math.isfinite(condition) else None,
    }


def coordinate_audit(model, x, steps, base_score, analytic_gradient):
    numerical, curvature = [], []
    for axis, step in enumerate(np.asarray(steps, dtype=float)):
        delta = np.zeros(3)
        delta[axis] = step
        plus = float(model.evaluate(x + delta, gradient=False)["score"])
        minus = float(model.evaluate(x - delta, gradient=False)["score"])
        numerical.append((plus - minus) / (2.0 * step))
        curvature.append(-(plus - 2.0 * base_score + minus) / (step * step))
    numerical = np.asarray(numerical)
    return {
        "steps": np.asarray(steps).tolist(),
        "numerical_gradient": numerical.tolist(),
        "analytic_gradient": np.asarray(analytic_gradient).tolist(),
        "absolute_discrepancy": np.abs(numerical - analytic_gradient).tolist(),
        "max_absolute_discrepancy": float(np.max(np.abs(numerical - analytic_gradient))),
        "negative_curvature_diagonal_from_scores": curvature,
    }


def directional_probes(model, x, delta, scales, bounds):
    norm = float(np.linalg.norm(delta))
    direction = delta / norm if norm > 0.0 else np.zeros(3)
    rows = []
    for scale in scales:
        point = x + float(scale) * delta
        inside = bool(np.all(point >= bounds[:, 0]) and np.all(point <= bounds[:, 1]))
        row = {"scale": float(scale), "x": point.tolist(), "inside_bounds": inside}
        if inside:
            evaluated = model.evaluate(point, gradient=True)
            gradient = np.asarray(evaluated["gradient"], dtype=float)
            row.update(
                score=float(evaluated["score"]),
                gradient=gradient.tolist(),
                gradient_max_abs=float(np.max(np.abs(gradient))),
                directional_gradient=float(gradient @ direction),
                en_displacement_m=float(1000.0 * np.linalg.norm((point - x)[:2])),
                time_displacement_s=float(point[2] - x[2]),
            )
        rows.append(row)
    return rows


def all_finite(value):
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(all_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(all_finite(item) for item in value)
    return True


def main():
    started = time.monotonic()
    model, old, context, sources = load_case()
    fold = old["fold"]
    x = np.asarray(fold["x"], dtype=float)
    base_score = float(context["initial"]["score"])
    gradient = np.asarray(context["initial"]["gradient"], dtype=float)
    primary = hessian_summary(negative_hessian(model, x, STEPS))
    half = hessian_summary(negative_hessian(model, x, STEPS / 2.0))
    primary_symmetric = np.asarray(primary["symmetric"])
    half_symmetric = np.asarray(half["symmetric"])
    step_disagreement = float(
        np.linalg.norm(primary_symmetric - half_symmetric)
        / max(np.linalg.norm(half_symmetric), np.finfo(float).tiny)
    )
    delta = None
    try:
        solved = np.linalg.solve(primary_symmetric, gradient)
        if np.isfinite(solved).all():
            delta = solved
    except np.linalg.LinAlgError:
        pass
    probes = [] if delta is None else directional_probes(
        model, x, delta, (0.0, 0.5, 1.0, 2.0), context["bounds"]
    )
    audits = {
        label: coordinate_audit(model, x, steps, base_score, gradient)
        for label, steps in (
            ("double", 2.0 * STEPS),
            ("original", STEPS),
            ("half", 0.5 * STEPS),
        )
    }
    numerical = {
        "original_step_hessian": primary,
        "half_step_hessian": half,
        "step_halving_relative_disagreement": step_disagreement,
        "established_limits": {
            "relative_asymmetry": 0.005,
            "step_halving_relative_disagreement": 0.005,
            "condition_number": 1e10,
        },
        "stable_by_established_limits": bool(
            primary["positive_definite"]
            and half["positive_definite"]
            and primary["relative_asymmetry"] <= 0.005
            and half["relative_asymmetry"] <= 0.005
            and step_disagreement <= 0.005
            and primary["condition_number"] is not None
            and primary["condition_number"] <= 1e10
        ),
        "newton_solve_available": delta is not None,
        "newton_displacement": None if delta is None else delta.tolist(),
        "newton_en_displacement_m": None if delta is None else float(1000.0 * np.linalg.norm(delta[:2])),
        "newton_time_displacement_s": None if delta is None else float(delta[2]),
        "directional_probes": probes,
        "coordinate_score_difference_audits": audits,
    }
    finite = all_finite({"score": base_score, "gradient": gradient.tolist(), **numerical})
    result = {
        "schema": "ds11-source-loo-saved-endpoint-precision/v1",
        "reference_used": False,
        "position_fit_performed": False,
        "job_key": KEY,
        "x": x.tolist(),
        "score": base_score,
        "gradient": gradient.tolist(),
        "gradient_max_abs": float(np.max(np.abs(gradient))),
        "finite_checks_passed": bool(finite),
        "numerical": numerical,
        "elapsed_s": time.monotonic() - started,
        "sources": sources,
    }
    if not finite:
        raise ValueError("precision diagnostic produced nonfinite output")
    with (HERE / "result.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({
        "job_key": KEY,
        "stable": numerical["stable_by_established_limits"],
        "newton_en_displacement_m": numerical["newton_en_displacement_m"],
        "newton_time_displacement_s": numerical["newton_time_displacement_s"],
        "elapsed_s": result["elapsed_s"],
    }))


if __name__ == "__main__":
    main()
