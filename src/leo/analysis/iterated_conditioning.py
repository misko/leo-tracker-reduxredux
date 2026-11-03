"""Damped iterated-EKF conditioning against one original Gaussian prior."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from leo.analysis.gaussian_sum_location import GaussianComponent, Prediction

FloatArray = NDArray[np.float64]
Predictor = Callable[[FloatArray], Prediction]
Support = Callable[[FloatArray], bool]


@dataclass(frozen=True)
class IteratedConditioningConfig:
    max_iterations: int = 12
    objective_tolerance: float = 1e-8
    step_tolerance: float = 1e-7
    minimum_step_scale: float = 2.0**-16
    geographic_indices: tuple[int, ...] = ()
    maximum_geographic_step: float = 25.0


@dataclass(frozen=True)
class IteratedConditioningResult:
    component: GaussianComponent
    mode: FloatArray
    active_indices: tuple[int, ...]
    objectives: tuple[float, ...]
    iterations: int
    converged: bool
    rejected_steps: int


def _objective(
    state: FloatArray,
    prior_mean: FloatArray,
    prior_precision: FloatArray,
    active: NDArray[np.int64],
    observation: FloatArray,
    predictor: Predictor,
    support: Support | None,
) -> tuple[float, Prediction | None]:
    if support is not None and not support(state):
        return float("inf"), None
    try:
        prediction = predictor(state)
    except (ValueError, np.linalg.LinAlgError):
        return float("inf"), None
    if not prediction.eligible or prediction.mean.shape != observation.shape:
        return float("inf"), None
    residual = observation - prediction.mean
    try:
        chol = np.linalg.cholesky(prediction.covariance)
        solved = np.linalg.solve(chol, residual)
    except np.linalg.LinAlgError:
        return float("inf"), None
    displacement = state[active] - prior_mean[active]
    value = 0.5 * (
        displacement @ prior_precision @ displacement
        + solved @ solved
        + 2.0 * np.log(np.diag(chol)).sum()
    )
    return float(value), prediction


def condition_iterated(
    parent: GaussianComponent,
    observation: object,
    predictor: Predictor,
    config: IteratedConditioningConfig | None = None,
    *,
    active_indices: Sequence[int] | None = None,
    support: Support | None = None,
    initial_mode: object | None = None,
) -> IteratedConditioningResult:
    """Find a local posterior mode and condition once at its final linearization."""
    config = IteratedConditioningConfig() if config is None else config
    if config.max_iterations < 1 or config.minimum_step_scale <= 0.0:
        raise ValueError("iteration limits must be positive")
    if config.maximum_geographic_step <= 0.0:
        raise ValueError("maximum geographic step must be positive")
    observed = np.asarray(observation, dtype=np.float64)
    if observed.ndim != 1 or not observed.size or np.any(~np.isfinite(observed)):
        raise ValueError("observation must be a finite non-empty vector")
    current = (
        np.array(parent.mean, copy=True)
        if initial_mode is None
        else np.asarray(initial_mode, dtype=np.float64).copy()
    )
    if current.shape != parent.mean.shape or np.any(~np.isfinite(current)):
        raise ValueError("initial mode must be a finite vector matching the parent")
    if support is not None and not support(current):
        raise ValueError("initial mode is outside declared support")
    initial = predictor(current)
    if initial.mean.shape != observed.shape or initial.jacobian.shape[1] != parent.mean.size:
        raise ValueError("predictor dimensions differ from observation or parent")
    if active_indices is None:
        active = np.flatnonzero(np.any(initial.jacobian != 0.0, axis=0))
    else:
        active = np.asarray(tuple(active_indices), dtype=np.int64)
    if active.ndim != 1 or not active.size or len(set(active.tolist())) != active.size:
        raise ValueError("active indices must be non-empty and unique")
    if np.any(active < 0) or np.any(active >= parent.mean.size):
        raise ValueError("active index outside state dimension")
    prior_covariance = parent.covariance[np.ix_(active, active)]
    prior_precision = np.linalg.inv(prior_covariance)
    objective, prediction = _objective(
        current, parent.mean, prior_precision, active, observed, predictor, support
    )
    if prediction is None or not np.isfinite(objective):
        raise ValueError("initial prediction is infeasible")
    objectives = [objective]
    rejected = 0
    converged = False
    geographic = np.array(config.geographic_indices, dtype=np.int64)
    if np.any(~np.isin(geographic, active)):
        raise ValueError("geographic indices must be active coordinates")

    for _ in range(config.max_iterations):
        h = prediction.jacobian[:, active]
        residual = observed - prediction.mean
        r_inverse_h = np.linalg.solve(prediction.covariance, h)
        system = prior_precision + h.T @ r_inverse_h
        gradient = h.T @ np.linalg.solve(prediction.covariance, residual)
        gradient -= prior_precision @ (current[active] - parent.mean[active])
        step = np.linalg.solve(system, gradient)
        if geographic.size:
            positions = [int(np.flatnonzero(active == index)[0]) for index in geographic]
            norm = np.linalg.norm(step[positions])
            if norm > config.maximum_geographic_step:
                step *= config.maximum_geographic_step / norm
        if np.linalg.norm(step) <= config.step_tolerance:
            converged = True
            break
        scale = 1.0
        accepted = False
        while scale >= config.minimum_step_scale:
            trial = np.array(current, copy=True)
            trial[active] += scale * step
            trial_objective, trial_prediction = _objective(
                trial, parent.mean, prior_precision, active, observed, predictor, support
            )
            if trial_prediction is not None and trial_objective < objective:
                current, objective, prediction = trial, trial_objective, trial_prediction
                objectives.append(objective)
                accepted = True
                break
            rejected += 1
            scale *= 0.5
        if not accepted:
            break
        if objectives[-2] - objectives[-1] <= config.objective_tolerance:
            converged = True
            break

    h_full = prediction.jacobian
    cross_covariance = parent.covariance @ h_full.T
    innovation = h_full @ parent.covariance @ h_full.T + prediction.covariance
    innovation = (innovation + innovation.T) * 0.5
    gain = np.linalg.solve(innovation, cross_covariance.T).T
    covariance = parent.covariance - gain @ cross_covariance.T
    covariance = (covariance + covariance.T) * 0.5
    mean = np.array(parent.mean, copy=True)
    mean[active] = current[active]
    inactive = np.setdiff1d(np.arange(parent.mean.size), active)
    if inactive.size:
        mean[inactive] += (
            parent.covariance[np.ix_(inactive, active)]
            @ np.linalg.solve(prior_covariance, current[active] - parent.mean[active])
        )
    component = GaussianComponent(parent.weight, mean, covariance, parent.identity_history)
    mode = np.array(mean, copy=True)
    mode.setflags(write=False)
    return IteratedConditioningResult(
        component, mode, tuple(map(int, active)), tuple(objectives), len(objectives) - 1,
        converged, rejected
    )


def condition_joint_iterated(
    parent: GaussianComponent,
    observations: Sequence[object],
    predictors: Sequence[Predictor],
    config: IteratedConditioningConfig | None = None,
    *,
    active_indices: Sequence[int] | None = None,
    support: Support | None = None,
    initial_mode: object | None = None,
) -> IteratedConditioningResult:
    """Condition several independent observation blocks as one joint factor."""
    observed_blocks = tuple(np.asarray(value, dtype=np.float64) for value in observations)
    predictor_blocks = tuple(predictors)
    if not observed_blocks or len(observed_blocks) != len(predictor_blocks):
        raise ValueError("joint observations and predictors must be non-empty and equal length")
    if any(block.ndim != 1 or not block.size or np.any(~np.isfinite(block))
           for block in observed_blocks):
        raise ValueError("joint observations must be finite non-empty vectors")
    observation = np.concatenate(observed_blocks)

    def stacked_predictor(state: FloatArray) -> Prediction:
        predictions = tuple(predictor(state) for predictor in predictor_blocks)
        means = np.concatenate([prediction.mean for prediction in predictions])
        jacobian = np.concatenate([prediction.jacobian for prediction in predictions], axis=0)
        sizes = [prediction.mean.size for prediction in predictions]
        covariance = np.zeros((sum(sizes), sum(sizes)))
        offset = 0
        for prediction, size in zip(predictions, sizes, strict=True):
            covariance[offset : offset + size, offset : offset + size] = prediction.covariance
            offset += size
        return Prediction(
            means,
            jacobian,
            covariance,
            all(prediction.eligible for prediction in predictions),
        )

    return condition_iterated(
        parent,
        observation,
        stacked_predictor,
        config,
        active_indices=active_indices,
        support=support,
        initial_mode=initial_mode,
    )
