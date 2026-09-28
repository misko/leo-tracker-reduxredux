"""Shared position and transfer on timestamp-selected temporal panels."""

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

decay, unit_id, stage, start_id = sys.argv[1:]
decay = int(decay)
plan = json.loads((HERE / "plan.json").read_text())
spec = next(m for m in plan["models"] if m["decay_s"] == decay)
unit = next(u for u in spec["units"] if u["unit_id"] == unit_id)
target = stage.startswith("target")
groups = [
    g
    for g in spec["groups"]
    if (
        g["dataset_id"] == unit["excluded_dataset"]
        if target
        else g["dataset_id"] in unit["source_datasets"]
    )
]
documents = baseline.load_documents(
    {"config": plan["config"], "inputs": [i for g in groups for i in g["inputs"]]}
)
assert [d["session_id"] for d in documents] == [s for g in groups for s in g["session_ids"]]
parent = HERE / f"t{decay}" / unit_id
folder = parent / stage / start_id if stage.endswith("fit") else parent / stage

if stage.endswith("fit"):
    prior_path = ROOT / unit["previous_target_selection" if target else "previous_source_selection"]
    prior = json.loads(prior_path.read_text())
    candidates = [
        r["result"] for r in prior["runs"] if r["result"] is not None and r["result"]["qualified"]
    ]
    candidates.sort(key=lambda r: r["start_id"] != prior["selected"]["start_id"])
    assert candidates[0] == prior["selected"]
    assert all(r["session_ids"] == [d["session_id"] for d in documents] for r in candidates)
    position = np.asarray(
        json.loads((parent / "source-selection.json").read_text())["selected"]["x"][:2]
        if target
        else prior["selected"]["x"][:2]
    )
    records, timings, baseline_sum, chosen_sum = [], [], 0.0, 0.0
    for index, document in enumerate(documents):
        local = CovariancePosition([document], plan["config"], decay, baseline.Stationary)
        replays = []
        for candidate in candidates:
            timing = candidate["x"][index + 2]
            value = local.evaluate(np.r_[position, timing], gradient=False, held=False)["score"]
            assert np.isfinite(value)
            replays.append(
                {"start_id": candidate["start_id"], "timing_s": timing, "training_log_score": value}
            )
        chosen = max(replays, key=lambda r: r["training_log_score"])
        baseline_sum += replays[0]["training_log_score"]
        chosen_sum += chosen["training_log_score"]
        timings.append(chosen["timing_s"])
        records.append(
            {
                "session_id": document["session_id"],
                "replays": replays,
                "chosen": chosen,
                "training_gain": chosen["training_log_score"] - replays[0]["training_log_score"],
                "timing_change_s": chosen["timing_s"] - replays[0]["timing_s"],
            }
        )
        del local
    model = CovariancePosition(documents, plan["config"], decay, baseline.Stationary)
    seed = np.r_[position, timings]
    replay = model.evaluate(seed, gradient=False, held=False)["score"]
    assert abs(replay - chosen_sum) < 1e-7
    assert chosen_sum >= baseline_sum - 1e-7
    if not target:
        assert abs(baseline_sum - prior["selected"]["training_log_score"]) < 1e-7
    audit = {
        "position": position.tolist(),
        "prior_training_score_at_prior_position": prior["selected"]["training_log_score"],
        "baseline_training_score_at_current_position": baseline_sum,
        "recombined_training_score": replay,
        "recombination_gain": replay - baseline_sum,
        "seed": seed.tolist(),
        "records": records,
        "changed_records_over_0_1ms": sum(abs(r["timing_change_s"]) > 1e-4 for r in records),
    }
    with (folder / "timing-audit.json").open("x") as stream:
        json.dump(audit, stream, indent=2, allow_nan=False)
    if target:
        initial = seed[2:]
        bounds = [(-5, 5)] * len(documents)

        def objective(x):
            value, gradient = model.value_gradient(np.r_[position, x])
            return value, gradient[2:]
    else:
        initial = seed
        bounds = [(-12, 12)] * 2 + [(-5, 5)] * len(documents)
        objective = model.value_gradient
    fit = minimize(
        objective,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=bounds,
        options={
            "maxiter": 140,
            "maxfun": 200,
            "ftol": 1e-14,
            "gtol": 1e-8,
            "maxls": 30,
        },
    )
    assert -float(fit.fun) >= replay - 1e-7
    x = np.r_[position, fit.x] if target else fit.x
    boundary = any(
        min(abs(v - a), abs(v - b)) < 1e-3 for v, (a, b) in zip(fit.x, bounds, strict=True)
    )
    result = {
        "initial": initial.tolist(),
        "x": x.tolist(),
        "success": bool(fit.success),
        "message": str(fit.message),
        "boundary_hit": boundary,
        "gradient": (-fit.jac).tolist(),
        "training_log_score": -float(fit.fun),
        "evaluations": int(fit.nfev),
        "iterations": int(fit.nit),
        "qualified": bool(fit.success and not boundary and max(abs(fit.jac)) <= 0.01),
        "estimate": dict(zip(("latitude_deg", "longitude_deg"), model.coordinates(x), strict=True)),
    }
else:
    model = CovariancePosition(documents, plan["config"], decay, baseline.Stationary)
    selected = json.loads(
        (parent / ("target-selection.json" if target else "source-selection.json")).read_text()
    )["selected"]
    x = np.asarray(selected["x"])
    evaluation = model.evaluate(x, gradient=True, held=True)
    assert abs(evaluation["score"] - selected["training_log_score"]) < 1e-7
    audit = []
    if not target:
        for step in (1e-3, 5e-4):
            for axis in (0, 1):
                delta = np.eye(len(x))[axis] * step
                finite = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / (2 * step)
                error = abs(finite - evaluation["gradient"][axis])
                assert error < 0.002, error
                audit.append(
                    {
                        "axis": axis,
                        "step_km": step,
                        "numerical": finite,
                        "analytic": float(evaluation["gradient"][axis]),
                        "absolute_difference": error,
                    }
                )
    result = {
        "training_log_score": evaluation["score"],
        "held_log_score": sum(r["held_log_score"] for r in evaluation["rows"]),
        "rows": evaluation["rows"],
        "offset_stationarity": evaluation["offset_stationarity"],
        "full_training_gradient": evaluation["gradient"].tolist(),
        "position_gradient_check": audit,
    }
result.update(
    decay_s=decay,
    unit_id=unit_id,
    stage=stage,
    start_id=start_id,
    session_ids=[d["session_id"] for d in documents],
)
with (folder / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(decay, unit_id, stage, start_id, "complete", flush=True)
