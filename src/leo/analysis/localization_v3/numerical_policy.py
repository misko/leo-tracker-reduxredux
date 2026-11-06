"""Owned numerical recovery policy; no process-wide optimizer or phase patches.

Centered derivatives count every physical objective call within the original
240-call budget. The larger reference window changes numerical linearization,
not satellite priors or target phase integration support.
"""

import inspect
import json
from copy import deepcopy

import numpy as np
from scipy.optimize import OptimizeResult

from leo.analysis.localization_v3.phase_reference import phase_refresh, reference_domain
from leo.analysis.localization_v3.predictive_linear import linear_geometry


class NumericalPolicy:
    """Per-stage numerical policy with explicit problem ownership and receipts."""

    # Preserve the frozen numerical worker's contraction order as well as its
    # optimizer. Optimized contractions change some orbital posterior bits.
    joint_contraction_optimized = False

    def __init__(self, *, reference_limit_s=30, centered_lbfgsb=True):
        if reference_limit_s not in (15, 30):
            raise ValueError("explicit reference limit must be 15 or 30 s")
        self.reference_limit_s = reference_limit_s
        self.centered_lbfgsb = bool(centered_lbfgsb)
        self.receipt = dict(
            reference_limit_s=reference_limit_s,
            centered_lbfgsb=bool(centered_lbfgsb),
            extra_optimizer_rounds=0,
            physical_priors_and_target_phase_support_unchanged=True,
            reference_updates=[],
            optimizer_calls=[],
            problem_count=0,
        )

    def problem_created(self, problem):
        checked_domains(problem, problem.reference)
        self.receipt["problem_count"] += 1

    def refresh(self, problem, phases, reference, *, limit_s=15.0):
        if len(problem.labels) != len(np.asarray(reference)):
            raise ValueError("captured problem/reference shape mismatch")
        if not np.array_equal(np.asarray(problem.reference), np.asarray(reference)):
            raise ValueError("captured problem is not the phase-refresh reference owner")
        updated, check = phase_refresh(phases, reference, limit_s=self.reference_limit_s)
        check["next_reference_domain"] = checked_domains(problem, updated)
        check["actual_posterior_domain"] = checked_domains(problem, np.asarray(phases))
        check["numerical_reference_limit_s"] = self.reference_limit_s
        self.receipt["reference_updates"].append(dict(caller_limit_s=float(limit_s), **check))
        return updated, check

    def minimize(
        self,
        original,
        fun,
        x0,
        *,
        args=(),
        method=None,
        jac=None,
        hess=None,
        hessp=None,
        bounds=None,
        constraints=(),
        tol=None,
        callback=None,
        options=None,
    ):
        if not self.centered_lbfgsb or not bounded_position_call(
            method, x0, bounds, jac, constraints
        ):
            return original(
                fun,
                x0,
                args=args,
                method=method,
                jac=jac,
                hess=hess,
                hessp=hessp,
                bounds=bounds,
                constraints=constraints,
                tol=tol,
                callback=callback,
                options=options,
            )
        result = centered_minimize(
            original, fun, x0, args=args, bounds=bounds, options=options, callback=callback, tol=tol
        )
        self.receipt["optimizer_calls"].append(
            dict(
                start=np.asarray(x0, float).tolist(),
                endpoint=np.asarray(result.x).tolist(),
                success=bool(result.success),
                status=int(result.status),
                message=str(result.message),
                total_physical_objective_evaluations=int(result.nfev),
                cap=int(result.objective_evaluation_cap),
                gradient=np.asarray(result.jac).tolist(),
                gradient_available=bool(result.get("jac_available", True)),
                maxls=40,
                step_km=0.001,
            )
        )
        return result


def map_calibration_arms(context, operation, arms, mapper=None):
    """Run independent fits and reconcile only this policy's ordered receipts.

    The mapper is an ordered process (or serial) port, never a threaded map:
    each task temporarily installs its own policy in the context it inherits.
    Unknown policy implementations retain the historical serial behavior.
    No partial receipt is committed if a task or validation fails.
    """
    policy = context.get("numerical_policy")
    if mapper is None or (policy is not None and type(policy) is not NumericalPolicy):
        return list(map(operation, arms))
    if policy is None:
        return list(mapper(operation, arms))
    arms = tuple(arms)
    if arms != ("c0", "fitted_c"):
        raise ValueError("Exactly the ordered c0/fitted_c pair is required")
    before = deepcopy(policy.receipt)

    def exact(value):
        return json.dumps(value, sort_keys=True, allow_nan=False)

    def execute(arm):
        local = deepcopy(policy)
        context["numerical_policy"] = local
        try:
            return arm, operation(arm), local.receipt
        finally:
            context["numerical_policy"] = policy

    completed = list(mapper(execute, arms))
    if exact(policy.receipt) != exact(before):
        raise ValueError("Mapper mutated the owning numerical receipt")
    merged = deepcopy(before)
    lists = ("reference_updates", "optimizer_calls")
    constant = set(before) - {*lists, "problem_count"}
    values = []
    for expected, (arm, value, receipt) in zip(arms, completed, strict=True):
        if arm != expected:
            raise ValueError("Numerical arm results are out of order")
        if set(receipt) != set(before) or any(
            exact(receipt[k]) != exact(before[k]) for k in constant
        ):
            raise ValueError("Numerical policy configuration changed in child")
        for key in lists:
            n = len(before[key])
            if exact(receipt[key][:n]) != exact(before[key]):
                raise ValueError("Child rewrote existing numerical receipt")
            merged[key].extend(deepcopy(receipt[key][n:]))
        count = receipt["problem_count"]
        if type(count) is not int or count < before["problem_count"]:
            raise ValueError("Child problem count is invalid")
        merged["problem_count"] += count - before["problem_count"]
        values.append(value)
    policy.receipt.clear()
    policy.receipt.update(merged)
    return values


def check_problem(context, problem):
    policy = context.get("numerical_policy")
    if policy is not None:
        policy.problem_created(problem)


def refresh(context, problem, phases, reference):
    policy = context.get("numerical_policy")
    if policy is None:
        return phase_refresh(phases, reference)
    return policy.refresh(problem, phases, reference)


def minimize(context, original, *args, **kwargs):
    policy = context.get("numerical_policy")
    if policy is None:
        return original(*args, **kwargs)
    return policy.minimize(original, *args, **kwargs)


def bounded_position_call(method, x0, bounds, jac=None, constraints=()):
    if str(method).upper() != "L-BFGS-B" or jac is not None or constraints:
        return False
    try:
        x = np.asarray(x0, float)
        b = np.asarray(bounds, float)
        return bool(
            x.shape == (2,)
            and b.shape == (2, 2)
            and np.isfinite(x).all()
            and np.array_equal(b, np.array([[-12.5, 12.5], [-12.5, 12.5]]))
        )
    except (TypeError, ValueError):
        return False


def centered_minimize(original, fun, x0, *, args=(), bounds, options=None, callback=None, tol=None):
    """Same initial point/box; count all derivative calls under the original cap."""
    options = dict(options or {})
    cap = min(240, int(options.get("maxfun", 240)))
    if cap < 1:
        raise ValueError("positive objective-evaluation cap required")
    options.update(maxfun=cap, maxiter=min(48, int(options.get("maxiter", 48))), maxls=40)
    options.pop("eps", None)
    options.pop("finite_diff_rel_step", None)
    b = np.asarray(bounds, float)
    x0 = np.asarray(x0, float)
    memo = {}
    gradients = {}
    last = np.clip(x0, b[:, 0], b[:, 1])
    iteration_count = 0
    gradient_calls = 0

    class Budget(Exception):
        pass

    def evaluated(x):
        key = tuple(np.asarray(x, float))
        if key not in memo:
            if len(memo) >= cap:
                raise Budget("counted physical objective evaluation cap reached")
            value = float(fun(np.asarray(x, float), *args))
            if not np.isfinite(value):
                raise ValueError("finite physical objective required")
            memo[key] = value
        return memo[key]

    def jacobian(x):
        nonlocal gradient_calls
        gradient_calls += 1
        gradient = []
        h = 0.001
        for k in range(2):
            direction = np.eye(2)[k] * h
            if x[k] - h >= b[k, 0] and x[k] + h <= b[k, 1]:
                value = (evaluated(x + direction) - evaluated(x - direction)) / (2 * h)
            elif x[k] + 2 * h <= b[k, 1]:
                value = (
                    -3 * evaluated(x) + 4 * evaluated(x + direction) - evaluated(x + 2 * direction)
                ) / (2 * h)
            else:
                value = (
                    3 * evaluated(x) - 4 * evaluated(x - direction) + evaluated(x - 2 * direction)
                ) / (2 * h)
            gradient.append(value)
        value = np.asarray(gradient)
        gradients[tuple(x)] = value
        return value

    def accepted(x):
        nonlocal last, iteration_count
        last = np.asarray(x, float).copy()
        iteration_count += 1
        if callback is not None:
            if set(inspect.signature(callback).parameters) == {"intermediate_result"}:
                callback(intermediate_result=OptimizeResult(x=last.copy(), fun=evaluated(last)))
            else:
                callback(last.copy())

    try:
        result = original(
            evaluated,
            x0,
            method="L-BFGS-B",
            jac=jacobian,
            bounds=bounds,
            options=options,
            callback=accepted,
            tol=tol,
        )
        scipy_nfev = int(result.nfev)
    except Budget as exc:
        key = tuple(last)
        value = memo.get(key)
        if value is None:
            key = next(iter(memo))
            last = np.asarray(key, float)
            value = memo[key]
        gradient = gradients.get(key)
        result = OptimizeResult(
            x=last,
            fun=value,
            success=False,
            status=1,
            message=str(exc),
            nit=iteration_count,
            nfev=len(memo),
            njev=gradient_calls,
            jac=np.zeros(2) if gradient is None else gradient,
            hess_inv=np.eye(2),
            jac_available=gradient is not None,
        )
        scipy_nfev = None
    result.scipy_nfev = scipy_nfev
    result.nfev = len(memo)
    result.total_physical_objective_evaluations = len(memo)
    result.objective_evaluation_cap = cap
    result.centered_gradient_step_km = 0.001
    result.numerical_maxls = 40
    return result


def checked_domains(p, phases):
    domains = dict(curved=reference_domain(p.sky["time_s"], p.flat_times, p.flat_labels, phases))
    entries = getattr(p, "linear_entries", [])
    if entries:
        view, *_ = linear_geometry(p, entries)
        domains["predictive"] = reference_domain(
            p.sky["time_s"], view.flat_times, view.flat_labels, phases
        )
    if not all(v["in_domain"] for v in domains.values()):
        raise ValueError("numerical reference leaves frozen causal orbit bank; no extrapolation")
    return domains
