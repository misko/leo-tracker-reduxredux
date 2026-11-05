"""Bounded refinement with all original residual, alias and elevation gates.

Solver success does not establish acceptance. Callers independently replay the
original paired gates after the final phase refresh.
"""

import numpy as np
from scipy.optimize import minimize

from leo.analysis.localization_v3.event_position import (
    attach_event_predictive,
    cached,
    make_event_problem,
    summary,
)
from leo.analysis.localization_v3.history_policy import ARMS
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening


def noise_slacks(residual, times):
    """Positive iff every existing noise-screen inequality is satisfied."""
    r = np.asarray(residual, float)
    d = batch_noise_screen(r[None, :], times)
    return dict(
        mean=1 - float(d["mean_z"][0]) / 3,
        slope=1 - float(d["slope_z"][0]) / 3,
        quadratic=1 - float(d["quadratic_bic_gain"][0]) / 10,
        step=1 - float(d["maximum_step_z"][0]) / 4,
        lag1=1 - abs(float(d["lag1_acf"][0])) / (4 / np.sqrt(len(r))),
    )


def residual_slacks(residual, times):
    r = np.asarray(residual, float)
    return dict(rms=1 - float(np.sqrt(np.mean(r * r))) / 450, **noise_slacks(r, times))


def feasible_fit(objective, slacks, start, lower, upper, *, iterations=40):
    """Minimize the RF objective with fixed gates and a small numerical interior.

    Solver success alone never establishes compatibility. The best feasible
    visited point is retained even if SLSQP stops on its budget, and the caller
    must independently replay all original gates at the final refreshed phase.
    """
    x0, lo, hi = (np.asarray(v, float) for v in (start, lower, upper))
    if x0.shape != lo.shape or x0.shape != hi.shape or np.any(lo >= hi):
        raise ValueError("matching finite position bounds required")
    if not all(np.isfinite(v).all() for v in (x0, lo, hi)) or iterations < 1:
        raise ValueError("finite position and positive iteration budget required")
    x0 = np.clip(x0, lo, hi)
    origin = float(objective(x0))
    points = []
    cache = {}

    def evaluate(x):
        key = tuple(np.asarray(x, float))
        if key not in cache:
            score = float(objective(x))
            gate = np.asarray(slacks(x), float)
            if (
                gate.ndim != 1
                or not len(gate)
                or (not np.isfinite(gate).all())
                or (not np.isfinite(score))
            ):
                raise ValueError("finite objective and nonempty finite gate slacks required")
            cache[key] = (score, gate)
            if gate.min() >= 0:
                points.append((score, np.asarray(x, float).copy(), float(gate.min())))
        return cache[key]

    result = minimize(
        lambda x: evaluate(x)[0] - origin,
        x0,
        method="SLSQP",
        bounds=list(zip(lo, hi, strict=True)),
        constraints=[dict(type="ineq", fun=lambda x: evaluate(x)[1] - 1e-06)],
        options=dict(maxiter=iterations, ftol=1e-07, eps=0.001),
    )
    evaluate(result.x)
    chosen = min(points, key=lambda v: v[0]) if points else None
    endpoint = chosen[1] if chosen is not None else np.asarray(result.x)
    score, gate = evaluate(endpoint)
    return dict(
        parameters=endpoint,
        score=score,
        minimum_gate_slack=float(gate.min()),
        feasible=chosen is not None,
        solver_success=bool(result.success),
        solver_message=str(result.message),
        iterations=int(result.nit),
        evaluations=len(cache),
        numerical_interior=1e-06,
        finite_difference_step_km=0.001,
    )


def gate_slacks(p, x, entries=()):
    """Every original profile, conditional, alias, elevation and support gate."""
    scan, c, state = (p.scan, p.calculate(x), p.state(x))
    frequency, elevation = p.conditional_frequency(x)
    slacks = {}
    owners = {}
    for row, i, sl, alias in zip(p.rows, p.members, p.slices, p.alias, strict=True):
        t, active = (scan.tracks[i], p.keep[sl])
        if not active.any():
            continue
        times = t["times"][active]
        q = t["rf_hz"] / 11500000000.0
        observed = t["values"] - scan.hardware(t, state["beta"])
        observed -= q * scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1]
        terms = profile(observed[active], q * frequency[sl][active], *whitening(times))
        prefix = t["key"]
        values = dict(
            rms=1 - float(terms["rms"][0]) / 450,
            bias=1 - abs(float(terms["bias"][0])) / 3000,
            alias=0.5 - abs(int(terms["alias"][0]) - alias),
            elevation=float(elevation[sl][active].min()) / 10,
            **noise_slacks(terms["innovations"][0], times),
        )
        slacks.update({prefix + "/profile/" + k: v for k, v in values.items()})
        slacks.update(
            {
                prefix + "/conditional/" + k: v
                for k, v in residual_slacks(c["conditional_residual_hz"][sl][active], times).items()
            }
        )
        owners.setdefault(row["candidate_index"], set()).add((t["receiver"], t["channel"]))
    for j in p.supported:
        if j in owners:
            slacks["support/" + str(j)] = float(len(owners[j]) - 1.5)
    for entry, sl in zip(entries, getattr(p, "linear_slices", []), strict=True):
        t = scan.tracks[entry["track_index"]]
        raw = c["linear_raw_prediction_residual_hz"][sl]
        terms = profile(
            raw, np.zeros(len(raw)), *scan.white[entry["track_index"]], bias_sigma=300.0
        )
        values = dict(
            rms=1 - float(terms["rms"][0]) / 450,
            bias=1 - abs(float(terms["bias"][0])) / 3000,
            alias=0.5 - abs(int(terms["alias"][0])),
            elevation=float(c["linear_elevation"][sl].min()) / 10,
            **noise_slacks(terms["innovations"][0], t["times"]),
        )
        slacks.update({entry["component"] + "/linear/" + k: v for k, v in values.items()})
    return slacks


def _problem(scan, node, mask, arm, reference, powers, means, hyper, entries):
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
    attach_event_predictive(p, entries, powers)
    return cached(p)


def constrained(scan, node, mask, powers, means, hyper, entries, pair):
    output = {}
    for arm in ARMS:
        reference = np.asarray(pair[arm]["phase_reference"])
        x = np.asarray(pair[arm]["endpoint_east_north_km"])
        history = []
        for _epoch in range(5):
            p = _problem(scan, node, mask, arm, reference, powers, means, hyper, entries)
            fitted = feasible_fit(
                lambda z, p=p: p.calculate(z)["negative_twice_elbo"],
                lambda z, p=p: np.asarray(list(gate_slacks(p, z, entries).values())) - 0.01,
                x,
                p.lower,
                p.upper,
                iterations=40,
            )
            x = np.asarray(fitted["parameters"])
            phase = np.clip(p.state(x)["phases"][p.labels], -15, 15)
            history.append(dict(fit=fitted, phase_change_s=float(np.max(abs(phase - reference)))))
            reference = phase
        output[arm] = summary(p, x, entries)
        output[arm].update(
            history=history,
            final_phase_change_s=history[-1]["phase_change_s"],
            minimum_gate_slack=min(gate_slacks(p, x, entries).values()),
        )
    return output
