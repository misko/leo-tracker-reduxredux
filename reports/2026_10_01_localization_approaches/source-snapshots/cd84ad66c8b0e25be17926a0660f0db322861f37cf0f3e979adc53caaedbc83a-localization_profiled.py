"""Profiled nuisance coordinates for hard-association localization.

The public fit accepts and returns the original coordinates
``[east, north, clock, drift_0, drift_1, satellite_epochs...]``.  Internally it
uses effective satellite shifts ``clock + epoch`` and reconstructs the unique
minimum-prior split.  Receiver drift is updated by a shared IRLS quadratic
proposal; every proposal is accepted against the original robust MAP objective.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import numpy as np

from leo.analysis.greedy_joint_location import JointGreedyResult
from leo.analysis.localization_evaluation import LocalizationTrackPort
from leo.analysis.robust_likelihood import student_t_weight


def effective_shifts(state: np.ndarray) -> np.ndarray:
    """Return ``clock + satellite_epoch`` for an original-coordinate state."""
    state = np.asarray(state, dtype=float)
    if state.ndim != 1 or state.size < 6 or np.any(~np.isfinite(state)):
        raise ValueError("state must contain finite original localization coordinates")
    return state[2] + state[5:]


def effective_shift_precision(
    clock_precision: float, epoch_precision: np.ndarray
) -> np.ndarray:
    """Precision of the exact profiled diagonal clock/epoch quadratic.

    This is the diagonal-minus-rank-one inverse of
    ``diag(1 / epoch_precision) + 11' / clock_precision``.  Zero precisions are
    supported through the profile expression itself, including inactive but
    properly regularized catalogue coordinates.
    """
    epochs = np.asarray(epoch_precision, dtype=float)
    if (epochs.ndim != 1 or epochs.size == 0 or np.any(~np.isfinite(epochs))
            or np.any(epochs < 0) or not np.isfinite(clock_precision)
            or clock_precision < 0):
        raise ValueError("precisions must be finite and nonnegative")
    total = float(clock_precision + np.sum(epochs))
    if total <= 0:
        raise ValueError("clock/epoch gauge must be constrained by the prior")
    return np.diag(epochs) - np.outer(epochs, epochs) / total


def reconstruct_profiled_state(
    spatial: np.ndarray,
    drift: np.ndarray,
    shifts: np.ndarray,
    prior_precision: np.ndarray,
    prior_mean: np.ndarray | None = None,
) -> np.ndarray:
    """Reconstruct the minimum-prior original state at fixed effective shifts."""
    spatial = np.asarray(spatial, dtype=float)
    drift = np.asarray(drift, dtype=float)
    shifts = np.asarray(shifts, dtype=float)
    precision = np.asarray(prior_precision, dtype=float)
    size = 5 + shifts.size
    center = np.zeros(size) if prior_mean is None else np.asarray(prior_mean, dtype=float)
    if (spatial.shape != (2,) or drift.shape != (2,) or shifts.ndim != 1
            or shifts.size == 0 or precision.shape != (size,) or center.shape != (size,)
            or np.any(~np.isfinite(spatial)) or np.any(~np.isfinite(drift))
            or np.any(~np.isfinite(shifts)) or np.any(~np.isfinite(precision))
            or np.any(precision < 0) or np.any(~np.isfinite(center))):
        raise ValueError("invalid profiled state or prior")
    epoch_precision = precision[5:]
    denominator = float(precision[2] + np.sum(epoch_precision))
    if denominator <= 0:
        raise ValueError("clock/epoch gauge must be constrained by the prior")
    clock = (
        precision[2] * center[2]
        + np.dot(epoch_precision, shifts - center[5:])
    ) / denominator
    result = np.empty(size)
    result[:2] = spatial
    result[2] = clock
    result[3:5] = drift
    result[5:] = shifts - clock
    return result


def profile_reconstruction_jacobian(prior_precision: np.ndarray) -> np.ndarray:
    """Return ``d original_state / d [east, north, effective_shifts...]``."""
    precision = np.asarray(prior_precision, dtype=float)
    if precision.ndim != 1 or precision.size < 6:
        raise ValueError("prior_precision has invalid shape")
    epochs = precision[5:]
    denominator = float(precision[2] + np.sum(epochs))
    if denominator <= 0:
        raise ValueError("clock/epoch gauge must be constrained by the prior")
    clock_derivative = epochs / denominator
    result = np.zeros((precision.size, 2 + epochs.size))
    result[0, 0] = result[1, 1] = 1.0
    result[2, 2:] = clock_derivative
    result[5:, 2:] = np.eye(epochs.size) - clock_derivative[None, :]
    return result


def solve_shared_drift(
    observations: Sequence[np.ndarray],
    means: Sequence[np.ndarray],
    designs: Sequence[np.ndarray],
    covariances: Sequence[np.ndarray],
    weights: Sequence[float],
    prior_precision: np.ndarray,
    prior_mean: np.ndarray | None = None,
) -> np.ndarray:
    """Solve one shared two-coordinate weighted Gaussian drift system."""
    precision = np.asarray(prior_precision, dtype=float)
    center = np.zeros(2) if prior_mean is None else np.asarray(prior_mean, dtype=float)
    lengths = {len(observations), len(means), len(designs), len(covariances), len(weights)}
    if (len(lengths) != 1 or precision.shape != (2,) or center.shape != (2,)
            or np.any(~np.isfinite(precision)) or np.any(precision < 0)
            or np.any(~np.isfinite(center))):
        raise ValueError("invalid shared drift system")
    system = np.diag(precision)
    rhs = precision * center
    for observation, mean_without_drift, design, covariance, weight in zip(
        observations, means, designs, covariances, weights, strict=True
    ):
        y = np.asarray(observation, dtype=float)
        mean = np.asarray(mean_without_drift, dtype=float)
        matrix = np.asarray(design, dtype=float)
        noise = np.asarray(covariance, dtype=float)
        if (y.ndim != 1 or mean.shape != y.shape or matrix.shape != (y.size, 2)
                or noise.shape != (y.size, y.size) or not np.isfinite(weight)
                or weight < 0):
            raise ValueError("invalid shared drift contribution")
        solved_design = np.linalg.solve(noise, matrix)
        system += weight * matrix.T @ solved_design
        rhs += weight * matrix.T @ np.linalg.solve(noise, y - mean)
    return np.linalg.lstsq(system, rhs, rcond=1e-12)[0]


def fit_localization_profiled(
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
    """Fit the unchanged hard MAP objective in profiled timing coordinates."""
    x0 = np.array(initial, dtype=float, copy=True)
    precision = np.asarray(prior_precision, dtype=float)
    center = np.zeros_like(x0) if prior_mean is None else np.asarray(prior_mean, dtype=float)
    if (x0.ndim != 1 or x0.size < 6 or precision.shape != x0.shape
            or center.shape != x0.shape or np.any(~np.isfinite(x0))
            or np.any(~np.isfinite(precision)) or np.any(precision < 0)
            or np.any(~np.isfinite(center)) or not support(x0)):
        raise ValueError("invalid initial state or prior")
    if max_iterations < 1 or max_spatial_step <= 0:
        raise ValueError("iteration and spatial-step limits must be positive")
    if degrees_of_freedom is not None and (
        not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0
    ):
        raise ValueError("degrees_of_freedom must be finite and positive")
    ports = tuple(ports)
    if not ports:
        raise ValueError("at least one localization port is required")
    if any(port.priors_piecewise_constant is not True for port in ports):
        raise ValueError("localization ports require piecewise-constant branch priors")
    ids = [identifier for port in ports for identifier in port.observation_ids]
    if len(ids) != len(set(ids)):
        raise ValueError("physical observations must not be reused")

    shifts = effective_shifts(x0)
    drift = x0[3:5].copy()
    reconstruction = profile_reconstruction_jacobian(precision)
    reduced_center = np.r_[center[:2], center[2] + center[5:]]
    reduced_precision = np.zeros((2 + shifts.size, 2 + shifts.size))
    reduced_precision[:2, :2] = np.diag(precision[:2])
    reduced_precision[2:, 2:] = effective_shift_precision(precision[2], precision[5:])

    def rebuild(reduced: np.ndarray, beta: np.ndarray) -> np.ndarray:
        return reconstruct_profiled_state(
            reduced[:2], beta, reduced[2:], precision, center
        )

    reduced = np.r_[x0[:2], shifts]
    x = rebuild(reduced, drift)

    def scores(state: np.ndarray) -> tuple[np.ndarray, ...]:
        result = []
        for port in ports:
            values = np.asarray(port.score_all(state), dtype=float)
            if (values.shape != (int(port.candidate_count) + 1,)
                    or np.any(np.isnan(values)) or np.any(np.isposinf(values))):
                raise ValueError("association scorer returned invalid branch scores")
            result.append(values)
        return tuple(result)

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
            value = .5 * float(np.dot(precision * delta, delta))
            value -= sum(selected_score(port, state, index) for port, index in zip(
                ports, assigned, strict=True
            ))
            return value if np.isfinite(value) else np.inf
        except (ValueError, np.linalg.LinAlgError):
            return np.inf

    objectives: list[float] = []
    accepted_norms: list[float] = []
    associations: tuple[int, ...] = ()
    converged = False
    reason = "iteration_limit"
    iterations = 0

    for iteration in range(max_iterations):
        if deadline is not None and time.monotonic() >= deadline:
            reason = "wall_budget"
            break
        score_values = scores(x)
        assigned = tuple(int(np.argmax(value)) for value in score_values)
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
            raise ValueError("association update increased the physical objective")
        stable = assigned == associations
        associations = assigned
        iteration_start_value = value
        iteration_step_norm = 0.0
        selected = []
        for port, index in zip(ports, assigned, strict=True):
            if index == int(port.candidate_count):
                continue
            prediction = port.predict_selected(x, index)
            if not prediction.eligible:
                raise ValueError("selected prediction is ineligible")
            if prediction.jacobian.shape[1] != x.size:
                raise ValueError("prediction Jacobian has wrong state dimension")
            selected.append((port, prediction))
        if not selected:
            reason = "all_background"
            break

        # Conditional Student-t IRLS proposal for the shared receiver drift.
        weights = []
        for port, prediction in selected:
            residual = np.asarray(port.observation) - prediction.mean
            mahalanobis = float(residual @ np.linalg.solve(prediction.covariance, residual))
            weights.append(1.0 if degrees_of_freedom is None else student_t_weight(
                mahalanobis, residual.size, degrees_of_freedom
            ))
        proposed_drift = solve_shared_drift(
            [np.asarray(port.observation) for port, _ in selected],
            [prediction.mean - prediction.jacobian[:, 3:5] @ x[3:5]
             for _, prediction in selected],
            [prediction.jacobian[:, 3:5] for _, prediction in selected],
            [prediction.covariance for _, prediction in selected],
            weights, precision[3:5], center[3:5],
        )
        drift_delta = proposed_drift - drift
        for backtrack in range(18):
            trial_drift = drift + drift_delta * (.5 ** backtrack)
            trial = rebuild(reduced, trial_drift)
            trial_value = objective(trial, assigned)
            if trial_value < value:
                original_delta = trial - x
                x, drift, value = trial, trial_drift, trial_value
                objectives.append(value)
                drift_step_norm = float(np.linalg.norm(original_delta))
                accepted_norms.append(drift_step_norm)
                iteration_step_norm += drift_step_norm
                break

        # Refresh the local model after an accepted drift proposal.
        selected = [(port, port.predict_selected(x, index)) for port, index in
                    zip(ports, assigned, strict=True) if index != int(port.candidate_count)]
        if any(not prediction.eligible for _, prediction in selected):
            raise ValueError("selected prediction is ineligible")
        system = reduced_precision.copy()
        gradient = -reduced_precision @ (reduced - reduced_center)
        drift_system = np.diag(precision[3:5])
        drift_gradient = -precision[3:5] * (drift - center[3:5])
        cross = np.zeros((reduced.size, 2))
        for port, prediction in selected:
            jacobian = prediction.jacobian @ reconstruction
            drift_jacobian = prediction.jacobian[:, 3:5]
            residual = np.asarray(port.observation) - prediction.mean
            solved_residual = np.linalg.solve(prediction.covariance, residual)
            weight = 1.0
            if degrees_of_freedom is not None:
                weight = student_t_weight(
                    float(residual @ solved_residual), residual.size, degrees_of_freedom
                )
            system += weight * jacobian.T @ np.linalg.solve(
                prediction.covariance, jacobian
            )
            gradient += weight * jacobian.T @ solved_residual
            solved_drift = np.linalg.solve(prediction.covariance, drift_jacobian)
            drift_system += weight * drift_jacobian.T @ solved_drift
            drift_gradient += weight * drift_jacobian.T @ solved_residual
            cross += weight * jacobian.T @ solved_drift
        drift_cross = np.linalg.lstsq(drift_system, cross.T, rcond=1e-12)[0]
        drift_rhs = np.linalg.lstsq(drift_system, drift_gradient, rcond=1e-12)[0]
        step = np.linalg.lstsq(
            system - cross @ drift_cross,
            gradient - cross @ drift_rhs,
            rcond=1e-12,
        )[0]
        drift_step = np.linalg.lstsq(
            drift_system, drift_gradient - cross.T @ step, rcond=1e-12
        )[0]
        spatial_length = float(np.linalg.norm(step[:2]))
        if spatial_length > max_spatial_step:
            scale = max_spatial_step / spatial_length
            step *= scale
            drift_step *= scale
        original_step = rebuild(reduced + step, drift + drift_step) - x
        if stable and iteration_step_norm + np.linalg.norm(original_step) < 1e-5:
            converged = True
            reason = "stationary"
            break
        accepted = False
        for backtrack in range(18):
            trial_reduced = reduced + step * (.5 ** backtrack)
            trial_drift = drift + drift_step * (.5 ** backtrack)
            trial = rebuild(trial_reduced, trial_drift)
            trial_value = objective(trial, assigned)
            if trial_value < value:
                original_delta = trial - x
                x, reduced, drift, value = trial, trial_reduced, trial_drift, trial_value
                objectives.append(value)
                nonlinear_step_norm = float(np.linalg.norm(original_delta))
                accepted_norms.append(nonlinear_step_norm)
                iteration_step_norm += nonlinear_step_norm
                accepted = True
                break
        iterations = iteration + 1
        if not accepted:
            if np.linalg.norm(original_step) < 1e-12 and iteration_step_norm > 0:
                continue
            reason = "line_search_stalled"
            break
        if (stable and iteration_start_value - value < 1e-7
                and iteration_step_norm < 1e-4):
            converged = True
            reason = "objective_stable"
            break

    return JointGreedyResult(
        x, associations, tuple(objectives), converged, iterations, reason,
        tuple(accepted_norms),
    )
