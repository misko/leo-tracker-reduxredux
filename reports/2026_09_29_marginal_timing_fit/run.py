import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PREVIOUS = HERE.parent / "2026_09_29_scan_holdout"
sys.path.insert(0, str(PREVIOUS))
spec = importlib.util.spec_from_file_location("scan_runner", PREVIOUS / "run.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
from timing_model import marginal, training_scores  # noqa: E402


def main(key, direction):
    started = time.monotonic()
    saved_path = PREVIOUS / f"{key}_d{direction}.json"
    saved = json.loads(saved_path.read_text())
    for name, digest in saved["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    baseline = saved["arms"][0]
    assert (
        baseline["success"] and not baseline["boundary"] and baseline["projected_gradient"] <= 0.01
    )
    plan_path = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    plan = json.loads(plan_path.read_text())
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = previous.receiver.baseline.load_documents(
        dict(config=plan["config"], inputs=unit["group"]["inputs"])
    )
    source, target = previous.split(docs, direction)
    models = [
        previous.receiver.TrendMixturePosition(
            [d], plan["config"], previous.receiver.baseline.Stationary, 0.2
        )
        for d in source
    ]
    tests = [
        previous.receiver.TrendMixturePosition(
            [d], plan["config"], previous.receiver.baseline.Stationary, 0.2
        )
        for d in target
    ]
    x = np.array(baseline["x"][:2])
    replay_score, replay_gradient = 0.0, 0.0
    replay_times = np.array([-5.0, -2.375, 0.0, 1.125, 5.0])
    for model in models:
        scores, gradients = training_scores(model, x, replay_times)
        for i, t in enumerate(replay_times):
            scalar = model.evaluate([*x, t])
            replay_score = max(replay_score, abs(scores[i] - scalar["score"]))
            replay_gradient = max(
                replay_gradient, float(max(abs(gradients[i] - scalar["gradient"][:2])))
            )
    assert replay_score < 1e-7 and replay_gradient < 1e-5

    def objective(z, order=16):
        values = [marginal(m, z, order) for m in models]
        return -sum(v[0] for v in values), -np.sum([v[1] for v in values], axis=0)

    initial_score, initial_gradient = objective(x)
    print(
        key,
        direction,
        "initial marginal gradient",
        initial_gradient.tolist(),
        "elapsed",
        time.monotonic() - started,
        flush=True,
    )
    fit = minimize(
        objective,
        x,
        jac=True,
        method="L-BFGS-B",
        bounds=[(-12.0, 12.0)] * 2,
        options=dict(maxiter=30, maxfun=50, ftol=1e-13, gtol=1e-5, maxls=15),
    )
    audit_score, audit_gradient = objective(fit.x, 32)
    delta_score = abs(audit_score - fit.fun)
    delta_gradient = float(max(abs(audit_gradient - fit.jac)))
    differences = []
    for axis in range(2):
        p, m = fit.x.copy(), fit.x.copy()
        p[axis] += 0.001
        m[axis] -= 0.001
        numerical = (objective(p)[0] - objective(m)[0]) / 0.002
        differences.append(abs(numerical - fit.jac[axis]))
    target_scans = [
        dict(session_id=d["session_id"], **previous.marginal_scan(m, fit.x))
        for d, m in zip(target, tests, strict=True)
    ]
    refinement_path = PREVIOUS / "refinement.json"
    refinement = json.loads(refinement_path.read_text())
    for name, digest in refinement["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    baseline_target = 0.0
    for t in baseline["target_scans"]:
        refined = next(
            (
                r
                for r in refinement["rows"]
                if r["unit"] == key
                and r["direction"] == direction
                and r["sigma"] == 0
                and r["session_id"] == t["session_id"]
            ),
            None,
        )
        score = refined or t
        assert score["qualified"]
        baseline_target += score["log_score"]
    pg = float(max(abs(fit.jac)))
    boundary = bool(np.any(abs(fit.x) > 11.999))
    qualified = bool(
        fit.success
        and not boundary
        and pg <= 0.01
        and delta_score <= 0.01
        and delta_gradient <= 0.01
        and max(differences) <= 0.01
        and all(t["qualified"] for t in target_scans)
    )
    paths = [
        saved_path,
        plan_path,
        refinement_path,
        HERE / "run.py",
        HERE / "timing_model.py",
        HERE / "PROTOCOL.md",
    ]
    result = dict(
        unit=key,
        direction=direction,
        x=fit.x.tolist(),
        success=bool(fit.success),
        message=str(fit.message),
        iterations=int(fit.nit),
        evaluations=int(fit.nfev),
        qualified=qualified,
        boundary=boundary,
        projected_gradient=pg,
        gradient_audit=max(differences),
        quadrature_score_difference=delta_score,
        quadrature_gradient_difference=delta_gradient,
        scalar_score_replay=replay_score,
        scalar_gradient_replay=replay_gradient,
        initial_marginal_score=-initial_score,
        initial_gradient=(-initial_gradient).tolist(),
        final_marginal_score=-float(fit.fun),
        baseline_estimate_deg=baseline["estimate_deg"],
        estimate_deg=list(models[0].models[0].coordinates([*fit.x, 0.0])),
        target_scans=target_scans,
        target_gain=sum(t["log_score"] for t in target_scans) - baseline_target,
        elapsed_seconds=time.monotonic() - started,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / f"{key}_d{direction}.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(key, direction, qualified, pg, result["elapsed_seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
