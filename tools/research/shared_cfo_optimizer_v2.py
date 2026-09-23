"""Training-only monotone coordinate search for joint receiver CFO profiles."""

from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, minimize

from tools.research.joint_template_source_isolation import _design

FS = 2_500_000


def mapping(nominal, shared):
    if not shared:
        return np.eye(4), np.zeros(4)
    delta = nominal[1] - nominal[0]
    return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]]), np.r_[
        0.0, 0.0, delta.mean() - delta
    ]


def objective(response, templates, indices, parameters, matrix, offset):
    """Variable projection SSE and exact gradient in frequency (Hz)."""
    frequencies = (matrix @ parameters + offset).reshape(2, 2)
    value, gradient = 0.0, np.zeros((2, 2))
    for rx in (0, 1):
        design = _design(templates[rx], indices, frequencies[rx], FS)
        coefficient, _, rank, singular = np.linalg.lstsq(design, response[:, rx], rcond=None)
        if rank != design.shape[1] or singular[0] / singular[-1] > 1e6:
            raise ValueError("rank-deficient or ill-conditioned pilot design")
        residual = response[:, rx] - design @ coefficient
        value += float(np.vdot(residual, residual).real)
        for source in (0, 1):
            sl = slice(source * templates.shape[2], (source + 1) * templates.shape[2])
            derivative = 2j * np.pi * indices / FS * (design[:, sl] @ coefficient[sl])
            gradient[rx, source] = -2 * float(np.vdot(residual, derivative).real)
    return value, matrix.T @ gradient.ravel()


def fit(response, templates, indices, train, nominal, initial, shared):
    matrix, offset = mapping(nominal, shared)
    if shared:
        delta = nominal[1] - nominal[0]
        start = np.r_[initial[0], np.mean(delta + initial[1] - initial[0]) - np.mean(delta)]
    else:
        start = initial.ravel().copy()
    if np.any(abs(start) > 2500) or np.any(abs(matrix @ start + offset) > 2500):
        raise ValueError("infeasible frozen initializer")
    y = response[train]
    t = templates[:, :, :, train]
    n = indices[train]
    evaluations = 0

    def evaluate(p):
        nonlocal evaluations
        evaluations += 1
        return objective(y, t, n, p, matrix, offset)

    best = start.copy()
    best_value = evaluate(best)[0]
    history = [best_value]
    if shared:
        # Qualify shared starts from independent TRAINING peaks, never held errors.
        bootstrap = initial.ravel().copy()
        bootstrap_value = objective(y, t, n, bootstrap, np.eye(4), np.zeros(4))[0]
        for axis in range(4):
            winner = bootstrap.copy()
            for value in np.arange(-2500.0, 2501.0, 50.0):
                trial = bootstrap.copy()
                trial[axis] = value
                score = objective(y, t, n, trial, np.eye(4), np.zeros(4))[0]
                evaluations += 1
                if score < bootstrap_value:
                    bootstrap_value, winner = score, trial
            bootstrap = winner
        residual = bootstrap.reshape(2, 2)
        offsets = delta + residual[1] - residual[0] - delta.mean()
        for candidate_offset in (offsets.mean(), *offsets):
            trial = np.r_[residual[0], candidate_offset]
            if np.any(abs(trial) > 2500) or np.any(abs(matrix @ trial + offset) > 2500):
                continue
            score = evaluate(trial)[0]
            if score < best_value:
                best, best_value = trial, score
        history.append(best_value)
    for _ in range(2):
        for axis in range(len(best)):
            rest = matrix @ best + offset - matrix[:, axis] * best[axis]
            active = matrix[:, axis] != 0
            lower = max(-2500.0, float(np.max((-2500 - rest[active]) / matrix[active, axis])))
            upper = min(2500.0, float(np.min((2500 - rest[active]) / matrix[active, axis])))
            winner = best.copy()
            for value in np.arange(-2500.0, 2501.0, 50.0):
                if not lower <= value <= upper:
                    continue
                trial = best.copy()
                trial[axis] = value
                score = evaluate(trial)[0]
                if score < best_value:
                    best_value = score
                    winner = trial
            best = winner
            history.append(best_value)
    scale = 50.0
    energy = max(float(np.sum(abs(y) ** 2)), 1e-30)

    def scaled(p):
        value, gradient = evaluate(p * scale)
        return value / energy, gradient * scale / energy

    result = minimize(
        scaled,
        best / scale,
        jac=True,
        method="SLSQP",
        bounds=Bounds(-2500 / scale, 2500 / scale),
        constraints=[LinearConstraint(matrix * scale, -2500 - offset, 2500 - offset)],
        options=dict(maxiter=100, ftol=1e-12),
    )
    candidate = result.x * scale
    feasible = (
        np.all(np.isfinite(candidate))
        and np.all(abs(candidate) <= 2500 + 1e-7)
        and np.all(abs(matrix @ candidate + offset) <= 2500 + 1e-7)
    )
    score = evaluate(candidate)[0] if feasible else float("inf")
    accepted = score < best_value
    if accepted:
        best, best_value = candidate, score
    history.append(best_value)
    frequencies = (matrix @ best + offset).reshape(2, 2)
    rows = []
    for rx in (0, 1):
        design = _design(t[rx], n, frequencies[rx], FS)
        coefficient = np.linalg.lstsq(design, y[:, rx], rcond=None)[0]
        held = _design(templates[rx][:, :, ~train], indices[~train], frequencies[rx], FS)
        error = response[~train, rx] - held @ coefficient
        rows.append(
            dict(
                train_sse=float(np.sum(abs(y[:, rx] - design @ coefficient) ** 2)),
                held_sse=float(np.sum(abs(error) ** 2)),
                coefficients=[[float(z.real), float(z.imag)] for z in coefficient],
            )
        )
    return dict(
        shared=shared,
        residual_cfo_hz=frequencies.tolist(),
        train_sse=best_value,
        receivers=rows,
        training_objective_history=history,
        evaluations=evaluations,
        local_success=bool(result.success),
        local_message=str(result.message),
        local_accepted=bool(accepted),
        boundary_hit=bool(np.any(abs(frequencies) >= 2499.9)),
    )
