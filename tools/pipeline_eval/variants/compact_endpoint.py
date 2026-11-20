"""Carry the exact accepted compact fit posterior into its reporting consumers."""

import hashlib
import json
from collections import Counter
from contextvars import ContextVar
from time import process_time_ns
from weakref import ref

import numpy as np

_endpoint = ContextVar("compact_accepted_endpoint", default=None)
_trace = ContextVar("compact_endpoint_trace", default=None)


def reset(enabled):
    _endpoint.set(None)
    _trace.set((enabled, Counter(), hashlib.sha256()))


def receipt():
    enabled, totals, digest = _trace.get()
    _endpoint.set(None)
    return dict(totals, enabled=enabled, fit_trajectory_sha256=digest.hexdigest())


def _coord(point):
    return np.asarray(point, dtype="<f8").tobytes()


def _binding(problem):
    calculate = problem.__dict__.get("calculate")
    return (
        None if calculate is None else ref(calculate),
        problem.keep.tobytes(),
        _coord(problem.reference),
        _coord(problem.phase_sigma),
        tuple(problem.alias),
        problem.fitted_c,
    )


def endpoint(problem, x):
    trace = _trace.get()
    frozen = _endpoint.get()
    if trace is None or not trace[0]:
        return problem.calculate(x)
    _, stats, _ = trace
    if frozen is not None:
        owner, point, binding, value = frozen
        if owner() is problem and point == _coord(x) and binding == _binding(problem):
            stats["reporting_calculations_saved"] += 1
            return value
        stats["reporting_recomputed"] += 1
    return problem.calculate(x)


def optimize(problem, optimizer, start, iterations):
    """Intercept only this fit's complete evaluations and retain the accepted exact value."""
    trace = _trace.get()
    _endpoint.set(None)
    if trace is None:
        return optimizer(
            problem.residual, start, problem.lower, problem.upper, iterations=iterations
        )
    enabled, stats, digest = trace
    enabled = enabled and not getattr(problem, "_has_fit_cache", False)
    stats["fits"] += 1
    original = problem.calculate
    prior = problem.__dict__.get("calculate")
    latest = accepted = None

    def observed(x):
        nonlocal latest
        value = original(x)
        latest = (_coord(x), value)
        stats["fit_full_calculations"] += 1
        return value

    def accept(x):
        nonlocal accepted
        if latest is not None and latest[0] == _coord(x):
            accepted = latest

    if enabled:
        problem.calculate = observed
    started = process_time_ns()
    try:
        callback = {"on_accept": accept} if enabled else {}
        fit = optimizer(
            problem.residual, start, problem.lower, problem.upper, iterations=iterations, **callback
        )
    finally:
        if enabled:
            if prior is None:
                del problem.calculate
            else:
                problem.calculate = prior
    stats["optimizer_cpu_ns"] += process_time_ns() - started
    stats["optimizer_evaluations"] += fit["evaluations"]
    digest.update(
        json.dumps(
            dict(
                c=problem.fitted_c,
                members=[int(i) for i in problem.members],
                families=[int(r["candidate_index"]) for r in problem.rows],
                aliases=[int(i) for i in problem.alias],
                keep=problem.keep.tobytes().hex(),
                reference=problem.reference.tolist(),
                sigma=problem.phase_sigma.tolist(),
                path=[(x["parameters"].tolist(), x["score"]) for x in fit["history"]],
                evaluations=fit["evaluations"],
                stopped=fit["stopped"],
                jacobian_refreshes=fit["jacobian_refreshes"],
                secant_updates=fit["secant_updates"],
                rejected_trials=fit["rejected_trials"],
            ),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    )
    if enabled and accepted is not None and accepted[0] == _coord(fit["parameters"]):
        _endpoint.set((ref(problem), accepted[0], _binding(problem), accepted[1]))
        stats["resolved_endpoints"] += 1
    return fit
