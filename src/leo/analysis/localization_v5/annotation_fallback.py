"""Bounded annotation training with a full original-start reference fallback."""

from copy import deepcopy

import numpy as np

from leo.analysis.localization_v3 import position
from leo.analysis.localization_v5 import annotation_training
from leo.contracts.localization_v5 import ANNOTATION_FALLBACK_POLICY, annotation_training_policy


def fit(problem, start=(0.0, 0.0), iterations=48):
    """Preserve successful primary fits and rerun unsuccessful fits with original GN."""
    policy = annotation_training_policy(ANNOTATION_FALLBACK_POLICY)
    original_start = np.asarray(start, float).copy()
    primary = annotation_training.fit(problem, original_start.copy(), iterations=iterations)
    attempts = [dict(optimizer="lbfgsb", **{key: deepcopy(primary[key]) for key in (
        "evaluations", "stopped", "budget_exhausted", "converged", "scipy_result",
        "score_correction", "stationarity", "solution_origin")})]
    history = [dict(deepcopy(row), attempt=0, optimizer="lbfgsb")
               for row in primary["history"]]
    fallback = dict(attempted=False, completed=False, evaluations=0,
                    stopped=None, budget_exhausted=False)
    result = dict(primary)
    reference_history = []
    metadata_calls = primary["final_metadata_calculate_calls"]

    if not primary["converged"]:
        calls = []
        residual_size = None
        reference_metadata_calls = 0

        class RecordedProblem:
            def __getattr__(self, name):
                return getattr(problem, name)

            def residual(self, at):
                nonlocal residual_size
                if len(calls) >= policy["fallback"]["residual_call_cap"]:
                    raise RuntimeError("Reference GN physical residual call cap exceeded")
                point = np.asarray(at, float).copy()
                if (point.shape != (2,) or not np.isfinite(point).all()
                        or np.any(point < problem.lower) or np.any(point > problem.upper)):
                    raise ValueError("Finite bounded two-dimensional reference evaluation required")
                value = np.asarray(problem.residual(point.copy()), float)
                if value.ndim != 1 or not value.size or not np.isfinite(value).all():
                    raise ValueError("Nonempty finite one-dimensional reference residual required")
                if residual_size is None:
                    residual_size = value.size
                elif residual_size != value.size:
                    raise ValueError("Invariant reference residual length required")
                with np.errstate(over="ignore", invalid="ignore"):
                    score = float(value @ value)
                if not np.isfinite(score):
                    raise ValueError("Finite reference residual objective required")
                calls.append(dict(parameters=point, score=score, attempt=1,
                                  optimizer="original_gn"))
                return value

            def calculate(self, at):
                nonlocal reference_metadata_calls
                reference_metadata_calls += 1
                calculated = problem.calculate(at)
                conditional = np.asarray(calculated["conditional_residual_hz"], float)
                keep = np.asarray(problem.keep)
                if (conditional.ndim != 1 or keep.shape != conditional.shape
                        or keep.dtype != np.bool_ or not keep.any()
                        or not np.isfinite(conditional).all()):
                    raise ValueError(
                        "Finite reference residuals and matching boolean mask required")
                return calculated

        reference = position.fit(RecordedProblem(), original_start.copy(), iterations=iterations)
        if reference["evaluations"] != len(calls):
            raise ValueError("Reference GN evaluations must match physical residual calls")
        parameters = np.asarray(reference["parameters"], float)
        if (parameters.shape != (2,) or not np.isfinite(parameters).all()
                or np.any(parameters < problem.lower) or np.any(parameters > problem.upper)):
            raise ValueError("Finite bounded reference parameters required")
        for key in ("score", "residual_rms_hz", "normalization_constant", "negative_twice_elbo"):
            value = np.asarray(reference[key], float)
            if value.shape != () or not np.isfinite(value):
                raise ValueError("Finite scalar reference result required")
        if not any(np.array_equal(parameters, row["parameters"])
                   and reference["score"] == row["score"] for row in calls):
            raise ValueError("Reference result must match an evaluated point and score")
        reference_history = deepcopy(reference["history"])
        history.extend(calls)
        exhausted = reference["stopped"] == "iteration_budget"
        attempts.append(dict(optimizer="original_gn", evaluations=len(calls),
                             stopped=reference["stopped"], budget_exhausted=exhausted,
                             converged=None, reference_fit_completed=True))
        fallback = dict(attempted=True, completed=True, evaluations=len(calls),
                        stopped=reference["stopped"], budget_exhausted=exhausted)
        result.update(reference, converged=None,
                      convergence_kind="original GN has no explicit convergence flag",
                      solution_origin="full original GN from original phase start",
                      stationarity=dict(source="original GN endpoint; stationarity not measured",
                                        projected_gradient_inf_norm=None, gtol=None,
                                        satisfied=None),
                      score_correction=None,
                      budget_exhausted=primary["budget_exhausted"] or exhausted)
        metadata_calls += reference_metadata_calls

    if len(history) > policy["total_residual_call_cap"]:
        raise RuntimeError("Composite physical residual call cap exceeded")
    result.update(optimizer_policy=deepcopy(policy), history_kind=policy["history_kind"],
                  history=history, evaluations=len(history), attempts=attempts, fallback=fallback,
                  reference_fit_completed=fallback["completed"],
                  reference_optimizer_history=reference_history,
                  reference_optimizer_history_kind="accepted iterates from original GN",
                  final_metadata_calculate_calls=metadata_calls,
                  scipy_result_scope="primary optimizer attempt",
                  physical_budget_exhausted=len(history) >= policy["total_residual_call_cap"])
    return result


fit.policy = annotation_training_policy(ANNOTATION_FALLBACK_POLICY)
