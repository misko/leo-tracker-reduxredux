"""Bounded hard-association localization over a narrow evaluation port.

This is the numerical policy of :mod:`leo.analysis.greedy_joint_location` with
objective evaluation delegated to full branch-score ports.  It is a local mode
search, not posterior integration.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import numpy as np

from leo.analysis.greedy_joint_location import JointGreedyResult
from leo.analysis.localization_evaluation import LocalizationTrackPort
from leo.analysis.robust_likelihood import student_t_weight


def fit_localization_fast(
    initial: np.ndarray,
    ports: Sequence[LocalizationTrackPort],
    prior_precision: np.ndarray,
    support: Callable[[np.ndarray], bool],
    *,
    max_iterations: int = 24,
    max_spatial_step: float = 25.0,
    deadline: float | None = None,
    prior_mean: np.ndarray | None = None,
    degrees_of_freedom: float | None = None,
) -> JointGreedyResult:
    """Alternate exact hard association with damped joint robust refitting.

    Each score port must return one normalized log joint per satellite followed
    by background.  Line searches keep the current assignments fixed but retain
    full-catalogue scoring so visibility-dependent background normalization is
    unchanged.
    """
    x = np.array(initial, dtype=float, copy=True)
    precision = np.asarray(prior_precision, dtype=float)
    center = np.zeros_like(x) if prior_mean is None else np.asarray(prior_mean, dtype=float)
    if (
        x.ndim != 1
        or precision.shape != x.shape
        or center.shape != x.shape
        or np.any(~np.isfinite(x))
        or np.any(~np.isfinite(precision))
        or np.any(~np.isfinite(center))
        or np.any(precision < 0)
        or not support(x)
    ):
        raise ValueError("invalid initial state or prior")
    if max_iterations < 1 or max_spatial_step <= 0:
        raise ValueError("iteration and spatial-step limits must be positive")
    if degrees_of_freedom is not None and (
        not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0
    ):
        raise ValueError("degrees_of_freedom must be finite and positive")
    if not ports:
        raise ValueError("at least one track port is required")
    ids = [identifier for port in ports for identifier in port.observation_ids]
    if len(ids) != len(set(ids)):
        raise ValueError("physical observations must not be reused")

    objectives: list[float] = []
    associations: tuple[int, ...] = ()
    reason = "iteration_limit"
    converged = False
    iterations = 0
    accepted_step_norms: list[float] = []

    def scores(port: LocalizationTrackPort, state: np.ndarray) -> np.ndarray:
        values = np.asarray(port.score_all(state), dtype=float)
        if (
            values.shape != (port.candidate_count + 1,)
            or np.any(np.isnan(values))
            or np.any(np.isposinf(values))
        ):
            raise ValueError("association scorer returned invalid branch scores")
        return values

    def selected_score(
        port: LocalizationTrackPort, state: np.ndarray, index: int
    ) -> float:
        value = float(port.score_selected(state, index))
        if np.isnan(value) or np.isposinf(value):
            raise ValueError("selected branch scorer returned an invalid score")
        return value

    def objective(state: np.ndarray, assigned: tuple[int, ...]) -> float:
        if not support(state):
            return np.inf
        try:
            delta = state - center
            value = 0.5 * np.dot(precision * delta, delta)
            for port, index in zip(ports, assigned, strict=True):
                value -= selected_score(port, state, index)
            return float(value)
        except (ValueError, np.linalg.LinAlgError):
            return np.inf

    for iteration in range(max_iterations):
        if deadline is not None and time.monotonic() >= deadline:
            reason = "wall_budget"
            break
        score_values = [scores(port, x) for port in ports]
        assigned = tuple(int(np.argmax(values)) for values in score_values)
        for port, index, values in zip(ports, assigned, score_values, strict=True):
            physical = selected_score(port, x, index)
            if not np.isclose(values[index], physical, rtol=1e-9, atol=1e-8):
                raise ValueError("association scorer disagrees with selected physical score")
        value = objective(x, assigned)
        if not np.isfinite(value):
            reason = "infeasible_assignment"
            break
        if not objectives:
            objectives.append(value)
        elif value > objectives[-1] + 1e-6:
            raise ValueError("association scorer disagrees with physical objective")

        active = {int(index) for index in np.flatnonzero(x)}
        predictions = []
        for port, index in zip(ports, assigned, strict=True):
            if index == port.candidate_count:
                continue
            prediction = port.predict_selected(x, index)
            if not prediction.eligible:
                raise ValueError("selected prediction is ineligible")
            active.update(map(int, np.flatnonzero(np.any(prediction.jacobian != 0.0, axis=0))))
            predictions.append((port, prediction))
        stable = assigned == associations
        associations = assigned
        if not predictions:
            reason = "all_background"
            break

        active_array = np.array(sorted(active), dtype=int)
        system = np.diag(precision[active_array])
        gradient = -precision[active_array] * (x[active_array] - center[active_array])
        for port, prediction in predictions:
            h = prediction.jacobian[:, active_array]
            residual = port.observation - prediction.mean
            solved_residual = np.linalg.solve(prediction.covariance, residual)
            weight = 1.0
            if degrees_of_freedom is not None:
                weight = student_t_weight(
                    float(residual @ solved_residual), residual.size, degrees_of_freedom
                )
            system += weight * h.T @ np.linalg.solve(prediction.covariance, h)
            gradient += weight * h.T @ solved_residual
        step = np.linalg.lstsq(system, gradient, rcond=1e-12)[0]
        spatial = [position for position, index in enumerate(active_array) if index in (0, 1)]
        length = np.linalg.norm(step[spatial])
        if length > max_spatial_step:
            step *= max_spatial_step / length
        if stable and np.linalg.norm(step) < 1e-5:
            converged = True
            reason = "stationary"
            break
        accepted = False
        for backtrack in range(18):
            trial = x.copy()
            trial[active_array] += step * (0.5**backtrack)
            trial_value = objective(trial, assigned)
            if trial_value < value:
                x = trial
                objectives.append(trial_value)
                accepted_step_norms.append(float(np.linalg.norm(step * (0.5**backtrack))))
                accepted = True
                break
        iterations = iteration + 1
        if not accepted:
            reason = "line_search_stalled"
            break
        if stable and value - trial_value < 1e-7 and accepted_step_norms[-1] < 1e-4:
            converged = True
            reason = "objective_stable"
            break

    return JointGreedyResult(
        x,
        associations,
        tuple(objectives),
        converged,
        iterations,
        reason,
        tuple(accepted_step_norms),
    )
