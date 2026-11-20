"""Check a coarse Armijo stop with two bounded, symmetric linearizations."""

import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import v5_armijo_fit as armijo

CHECK_KM = 0.001
CHECK_ROUNDS = 2


def bounded_armijo_tail(residual, initial, lower, upper, *, iterations=24, step=1e-3):
    fit = armijo.bounded_armijo(residual, initial, lower, upper, iterations=iterations, step=step)
    if fit["stopped"] != "small_bounded_step":
        return fit
    x, lo, hi = fit["parameters"], np.asarray(lower), np.asarray(upper)
    r, score = residual(x), fit["score"]
    fit["evaluations"] += 1
    fit["stopped"] = "centered_budget"
    for _ in range(CHECK_ROUNDS):
        jacobian = np.empty((len(r), 2))
        for axis in range(2):
            left, right = x.copy(), x.copy()
            left[axis], right[axis] = max(lo[axis], x[axis] - step), min(hi[axis], x[axis] + step)
            near_left = residual(left) if left[axis] < x[axis] else r
            near_right = residual(right) if right[axis] > x[axis] else r
            jacobian[:, axis] = (near_right - near_left) / (right[axis] - left[axis])
            fit["evaluations"] += int(left[axis] < x[axis]) + int(right[axis] > x[axis])
        fit["jacobian_refreshes"] += 1
        normal, gradient = jacobian.T @ jacobian, jacobian.T @ r
        normal += 1e-8 * np.diag(np.maximum(np.diag(normal), 1e-6))
        delta = armijo._step(normal, gradient, lo - x, hi - x)
        if np.linalg.norm(delta) <= CHECK_KM:
            fit["stopped"] = "centered_small_step"
            break
        previous_size = np.inf
        for _trial in range(armijo.TRIALS):
            trial = np.clip(x + delta, lo, hi)
            movement = trial - x
            size = np.max(np.abs(movement))
            if not 0 < size < previous_size:
                break
            rr = residual(trial)
            fit["evaluations"] += 1
            candidate = float(rr @ rr)
            if candidate < score - armijo.MIN_DECREASE and candidate <= score + 2 * armijo.ARMIJO * (
                gradient @ movement
            ):
                x, r, score = trial, rr, candidate
                fit["history"].append(dict(parameters=x.copy(), score=score))
                break
            previous_size = size
            delta *= 0.5
            fit["rejected_trials"] += 1
        else:
            size = 0
        if not 0 < size < previous_size:
            fit["stopped"] = "centered_no_descent"
            break
    return dict(fit, parameters=x, score=score)


def _num(value):
    return None if value is None or not np.isfinite(value) else float(value)


def _position(value):
    return None if value is None else np.asarray(value).tolist()


def _node(node):
    if node is None:
        return None
    return dict(
        tracks=[[str(row["component"]), int(row["candidate_index"]), bool(row["active_curvature"])]
                for row in node["seed"]["rows"]],
        aliases=[int(alias) for alias in node["aliases"]],
    )


def _mask(mask):
    if mask is None:
        return None
    keep = np.asarray(mask, dtype=bool)
    return dict(size=keep.size, retained=int(keep.sum()), sha256=sha256(keep.tobytes()).hexdigest())


def _arm(value):
    if value is None:
        return None
    record = value.get("record", value)
    fit = record.get("fit", record)
    point = record.get("endpoint_east_north_km", fit.get("parameters"))
    return dict(
        position_km=_position(point),
        score=_num(fit.get("score")),
        elbo=_num(record.get("negative_twice_elbo", fit.get("negative_twice_elbo"))),
        rf_rms_hz=_num(record.get("RMS_hz", fit.get("residual_rms_hz"))),
    )


def _stage(stage, output, fallback_node=None):
    node = output.get("node", output.get("final_node", output.get("baseline_node", fallback_node)))
    keep = output.get("keep", output.get("mask", output.get("final_mask", output.get("original_mask"))))
    grouped = {}
    for name in ("arms", "policy_arms", "curved_arms", "linear_arms", "baseline_arms"):
        if isinstance(output.get(name), dict):
            grouped[name] = {arm: _arm(output[name].get(arm)) for arm in ("c0", "fitted_c")}
    return dict(
        stage=stage,
        status=output.get("status"),
        accepted=None if output.get("accepted") is None else bool(output["accepted"]),
        signed_accepted=None if "accepted" not in (output.get("signed") or {})
        else bool(output["signed"]["accepted"]),
        assignments=_node(node),
        mask=_mask(keep),
        arm_groups=grouped,
        selection_gain=_num(output.get("selection_gain")),
        search_penalty=_num(output.get("search_penalty")),
        linear_paired_valid=None if "linear_paired_valid" not in output else bool(output["linear_paired_valid"]),
        linear_points=None if "linear_used_points" not in output else int(output["linear_used_points"]),
        linear_entries=[
            [str(e["component"]), int(e["candidate_index"]), int(e["alias"]), int(e["points"])]
            for e in output.get("linear_entries", output.get("entries", []))
        ],
        replacements=[
            [int(r["original_index"]), int(r["candidate_index"])]
            for r in (output.get("selected") or {}).get("replacements", [])
        ],
        nominations=[
            dict(original=int(f["original_index"]), best=int(f["best"]["candidate_index"])
                 if f.get("best") else None, gain=_num(f.get("predictive_gain")))
            for f in output.get("families", [])
        ],
    )


def worker(request, result, library, method, trace):
    import json

    from importlib import import_module

    from leo.analysis.localization_v3 import position

    from tools.pipeline_eval.variants import v5_core, v5_secant_fit
    from tools.pipeline_eval.variants.v5_secant_fit import save_json

    optimizer = {
        "stock": position.bounded_gauss_newton,
        "secant": v5_secant_fit.bounded_secant,
        "armijo": armijo.bounded_armijo,
        "tail": bounded_armijo_tail,
    }[method]
    timeline = []
    refresh = position.refreshed

    def branch(scan, sigma, node, arm, **kwargs):
        problem, fit, history = refresh(scan, sigma, node, arm, **kwargs)
        timeline.append(dict(
            stage="initial_branch", arm=arm, assignments=_node(node), mask=_mask(problem.keep),
            epochs=[_arm(epoch) | {"stop": epoch["fit"]["stopped"]} for epoch in history],
        ))
        return problem, fit, history

    def observer(label, function):
        def observe(*args, **kwargs):
            result = function(*args, **kwargs)
            if label == "initial_selection":
                choice = result[0]["choices"][0]
                timeline.append(_stage(label, dict(node=choice["node"], arms=choice["arms"])))
            else:
                fallback = args[1]["final_node"] if label == "history_policy" else None
                timeline.append(_stage(label, result, fallback))
            return result
        return observe

    with ExitStack() as scope:
        scope.enter_context(patch.object(position, "bounded_gauss_newton", optimizer))
        if trace == "trace":
            scope.enter_context(patch.object(position, "refreshed", branch))
            for name, module in [
                ("initial_selection", v5_core),
                *((n, import_module("leo.analysis.localization_v3." + n)) for n in
                  ("conservative_recovery", "history_policy", "signed_context")),
                *((n, import_module("leo.analysis.localization_v3.family_cavity")) for n in
                  ("nominate_families", "cavity_policy")),
            ]:
                scope.enter_context(patch.object(module, name, observer(name, getattr(module, name))))
        v5_secant_fit.worker(request, result, library, "reference")
    if trace == "trace":
        data = json.loads(Path(result).read_bytes())
        data["metrics"]["stage_trace"] = timeline
        save_json(Path(result), data)


def run(case, work_dir, method, trace=False):
    from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_secant_fit

    library = Path(work_dir) / "orbit_projector.so"
    library.parent.mkdir(parents=True, exist_ok=True)
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(
        case, work_dir, Path(__file__), worker_args=(str(library), method, "trace" if trace else "plain")
    )
    result["boundary"] = v5_secant_fit.BOUNDARY
    return result


if __name__ == "__main__":
    worker(*sys.argv[1:])
