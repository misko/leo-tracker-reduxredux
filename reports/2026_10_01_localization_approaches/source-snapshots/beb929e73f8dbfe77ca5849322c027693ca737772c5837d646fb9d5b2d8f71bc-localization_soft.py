"""Bounded soft-association optimization for single-scan localization.

This module searches for a local mode of a normalized log-sum-exp association
objective.  It is neither a posterior integrator nor a calibrated uncertainty
estimator.  Branch responsibilities and Student-t weights form an IRLS proposal;
every accepted step is checked against the complete soft objective returned by
the scoring ports.

The scoring port owns association/background priors and returns one normalized
log joint per catalogue candidate followed by the background log joint.  Its
``predict_selected`` method supplies the local measurement linearization for a
catalogue branch.  State-dependent association-prior derivatives are not part
of that port: the proposal treats those priors as locally constant, while the
full-objective line search still rejects steps crossing an adverse boundary.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from leo.analysis.robust_likelihood import student_t_weight


class SoftFactorPort(Protocol):
    """Minimal physics port consumed by :func:`fit_joint_soft`."""

    observation_ids: Sequence[str]
    observation: np.ndarray
    candidate_count: int
    priors_piecewise_constant: bool

    def score_all(self, state: np.ndarray) -> np.ndarray: ...

    def predict_selected(self, state: np.ndarray, index: int): ...


@dataclass(frozen=True)
class JointSoftResult:
    mean: np.ndarray
    responsibilities: tuple[np.ndarray, ...] | None
    objectives: tuple[float, ...]
    converged: bool
    iterations: int
    reason: str
    accepted_step_norms: tuple[float, ...]
    max_omitted_responsibility: float
    proposal_is_approximate: bool
    responsibilities_at_mean: bool
    admissible_for_official_benchmark: bool


class _DeadlineReached(RuntimeError):
    pass


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    if not np.isfinite(maximum):
        return -np.inf
    return float(maximum + np.log(np.exp(values - maximum).sum()))


def _scores(port: SoftFactorPort, state: np.ndarray) -> np.ndarray:
    values = np.asarray(port.score_all(state), dtype=float)
    expected = (int(port.candidate_count) + 1,)
    if values.shape != expected or np.any(np.isnan(values)) or np.any(np.isposinf(values)):
        raise ValueError("score_all returned invalid normalized log-joints")
    return values


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise _DeadlineReached


def _objective(
    state: np.ndarray,
    ports: Sequence[SoftFactorPort],
    center: np.ndarray,
    precision: np.ndarray,
    support: Callable[[np.ndarray], bool],
    deadline: float | None,
) -> float:
    if not support(state):
        return np.inf
    delta = state - center
    value = 0.5 * float(np.dot(precision * delta, delta))
    try:
        for port in ports:
            _check_deadline(deadline)
            evidence = _logsumexp(_scores(port, state))
            if not np.isfinite(evidence):
                return np.inf
            value -= evidence
    except (ValueError, np.linalg.LinAlgError):
        return np.inf
    return float(value)


def _responsibilities(values: np.ndarray) -> np.ndarray:
    evidence = _logsumexp(values)
    if not np.isfinite(evidence):
        raise ValueError("factor has zero finite association mass")
    result = np.exp(values - evidence)
    # Remove the final rounding error without changing branch ratios.
    result /= result.sum()
    return result


def _working_indices(
    probabilities: np.ndarray,
    candidate_count: int,
    max_active: int | None,
    omission_limit: float,
) -> tuple[np.ndarray, float, bool]:
    satellite = probabilities[:candidate_count]
    positive = np.flatnonzero(satellite > 0.0)
    if max_active is None or positive.size <= max_active:
        return positive, 0.0, False
    order = positive[np.argsort(satellite[positive])[::-1]]
    chosen = order[:max_active]
    omitted = float(satellite.sum() - satellite[chosen].sum())
    if omitted > omission_limit + 1e-15:
        return chosen, omitted, True
    return chosen, max(0.0, omitted), True


def fit_joint_soft(
    initial: np.ndarray,
    factors: Sequence[SoftFactorPort],
    prior_precision: np.ndarray,
    support: Callable[[np.ndarray], bool],
    *,
    max_iterations: int = 24,
    max_spatial_step: float = 25.0,
    deadline: float | None = None,
    prior_mean: np.ndarray | None = None,
    degrees_of_freedom: float = 4.0,
    max_active_branches_per_factor: int | None = None,
    max_omitted_responsibility: float = 1e-6,
) -> JointSoftResult:
    """Fit one local soft-association mode with a bounded IRLS search.

    The optional working set affects only the proposal.  Scores and every line
    search decision always use all catalogue branches and background.  If the
    exact responsibility mass omitted by the configured cap exceeds
    ``max_omitted_responsibility``, the method returns an explicit failed gate
    rather than renormalizing the retained branches. Omitted probability mass
    does not bound omitted gradient, so every capped run remains diagnostic and
    ineligible for the official benchmark. The default differentiates all
    finite candidate branches.
    """
    x = np.array(initial, dtype=float, copy=True)
    precision = np.asarray(prior_precision, dtype=float)
    center = np.zeros_like(x) if prior_mean is None else np.asarray(prior_mean, dtype=float)
    ports = tuple(factors)
    if (
        x.ndim != 1
        or precision.shape != x.shape
        or center.shape != x.shape
        or np.any(~np.isfinite(x))
        or np.any(~np.isfinite(precision))
        or np.any(~np.isfinite(center))
        or np.any(precision < 0.0)
        or not support(x)
    ):
        raise ValueError("invalid initial state or prior")
    if not ports:
        raise ValueError("at least one factor port is required")
    if max_iterations < 1 or not np.isfinite(max_spatial_step) or max_spatial_step <= 0.0:
        raise ValueError("iteration and spatial-step limits must be positive")
    if not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0.0:
        raise ValueError("degrees_of_freedom must be finite and positive")
    if max_active_branches_per_factor is not None and max_active_branches_per_factor < 1:
        raise ValueError("max_active_branches_per_factor must be positive or None")
    if (
        not np.isfinite(max_omitted_responsibility)
        or not 0.0 <= max_omitted_responsibility < 1.0
    ):
        raise ValueError("max_omitted_responsibility must be in [0, 1)")
    ids = [identifier for port in ports for identifier in port.observation_ids]
    if not ids or any(not identifier for identifier in ids) or len(ids) != len(set(ids)):
        raise ValueError("physical observation IDs must be non-empty and must not be reused")
    for port in ports:
        observation = np.asarray(port.observation, dtype=float)
        if observation.ndim != 1 or observation.size == 0 or np.any(~np.isfinite(observation)):
            raise ValueError("factor observations must be non-empty finite vectors")
        if int(port.candidate_count) < 0:
            raise ValueError("candidate_count must be non-negative")
        if getattr(port, "priors_piecewise_constant", None) is not True:
            raise ValueError(
                "factor port must declare priors_piecewise_constant=True; "
                "smooth prior gradients are unavailable through this protocol"
            )

    objectives: list[float] = []
    accepted_norms: list[float] = []
    final_responsibilities: tuple[np.ndarray, ...] | None = None
    largest_omission = 0.0
    used_working_set = False
    converged = False
    reason = "iteration_limit"
    iterations = 0

    for iteration in range(max_iterations):
        try:
            _check_deadline(deadline)
            score_values = tuple(_scores(port, x) for port in ports)
            responsibilities = tuple(_responsibilities(values) for values in score_values)
            value = _objective(x, ports, center, precision, support, deadline)
        except _DeadlineReached:
            reason = "wall_budget"
            break
        if not np.isfinite(value):
            reason = "infeasible_soft_objective"
            break
        final_responsibilities = tuple(np.array(item, copy=True) for item in responsibilities)
        if not objectives:
            objectives.append(value)
        elif value > objectives[-1] + 1e-6:
            raise ValueError("accepted state increased the full soft objective")

        branches: list[tuple[SoftFactorPort, int, float, object]] = []
        active_coordinates = set(map(int, np.flatnonzero(x - center)))
        gate_failed = False
        try:
            for port, probability in zip(ports, responsibilities, strict=True):
                _check_deadline(deadline)
                indices, omitted, truncated = _working_indices(
                    probability,
                    int(port.candidate_count),
                    max_active_branches_per_factor,
                    max_omitted_responsibility,
                )
                used_working_set |= truncated
                largest_omission = max(largest_omission, omitted)
                if omitted > max_omitted_responsibility + 1e-15:
                    gate_failed = True
                    break
                for index in indices:
                    prediction = port.predict_selected(x, int(index))
                    if not prediction.eligible:
                        if probability[index] > 1e-15:
                            raise ValueError("ineligible branch has positive responsibility")
                        continue
                    jacobian = np.asarray(prediction.jacobian, dtype=float)
                    observation = np.asarray(port.observation, dtype=float)
                    mean = np.asarray(prediction.mean, dtype=float)
                    covariance = np.asarray(prediction.covariance, dtype=float)
                    if (
                        mean.shape != observation.shape
                        or jacobian.shape != (observation.size, x.size)
                        or covariance.shape != (observation.size, observation.size)
                    ):
                        raise ValueError("prediction has incompatible dimensions")
                    active_coordinates.update(
                        map(int, np.flatnonzero(np.any(jacobian != 0.0, axis=0)))
                    )
                    branches.append((port, int(index), float(probability[index]), prediction))
        except _DeadlineReached:
            reason = "wall_budget"
            break
        if gate_failed:
            reason = "working_set_mass_exceeded"
            break
        if not branches:
            reason = "all_background"
            break

        active = np.array(sorted(active_coordinates), dtype=int)
        system = np.diag(precision[active])
        gradient = -precision[active] * (x[active] - center[active])
        try:
            for port, _index, responsibility, prediction in branches:
                _check_deadline(deadline)
                observation = np.asarray(port.observation, dtype=float)
                residual = observation - np.asarray(prediction.mean, dtype=float)
                covariance = np.asarray(prediction.covariance, dtype=float)
                solved_residual = np.linalg.solve(covariance, residual)
                mahalanobis = float(residual @ solved_residual)
                weight = responsibility * student_t_weight(
                    mahalanobis, residual.size, degrees_of_freedom
                )
                h = np.asarray(prediction.jacobian, dtype=float)[:, active]
                solved_h = np.linalg.solve(covariance, h)
                system += weight * h.T @ solved_h
                gradient += weight * h.T @ solved_residual
            step = np.linalg.lstsq(system, gradient, rcond=1e-12)[0]
        except _DeadlineReached:
            reason = "wall_budget"
            break
        except np.linalg.LinAlgError:
            reason = "linear_solve_failed"
            break
        spatial = [position for position, coordinate in enumerate(active) if coordinate in (0, 1)]
        spatial_length = float(np.linalg.norm(step[spatial]))
        if spatial_length > max_spatial_step:
            step *= max_spatial_step / spatial_length
        if np.linalg.norm(step) < 1e-5:
            converged = True
            reason = "stationary"
            break

        accepted = False
        trial_value = np.inf
        try:
            for backtrack in range(18):
                _check_deadline(deadline)
                trial = x.copy()
                trial[active] += step * (0.5**backtrack)
                trial_value = _objective(trial, ports, center, precision, support, deadline)
                if trial_value < value:
                    accepted_step = step * (0.5**backtrack)
                    x = trial
                    objectives.append(trial_value)
                    accepted_norms.append(float(np.linalg.norm(accepted_step)))
                    accepted = True
                    break
        except _DeadlineReached:
            reason = "wall_budget"
            break
        iterations = iteration + 1
        if not accepted:
            reason = "line_search_stalled"
            break
        if value - trial_value < 1e-7 and accepted_norms[-1] < 1e-4:
            converged = True
            reason = "objective_stable"
            break

    # Keep reported responsibilities aligned with the returned state. Do not
    # expose stale values or perform unbudgeted cleanup after a deadline.
    if reason != "wall_budget":
        final_responsibilities = tuple(
            _responsibilities(_scores(port, x)) for port in ports
        )
    else:
        final_responsibilities = None

    return JointSoftResult(
        mean=x,
        responsibilities=final_responsibilities,
        objectives=tuple(objectives),
        converged=converged,
        iterations=iterations,
        reason=reason,
        accepted_step_norms=tuple(accepted_norms),
        max_omitted_responsibility=largest_omission,
        proposal_is_approximate=used_working_set,
        responsibilities_at_mean=reason != "wall_budget",
        admissible_for_official_benchmark=not used_working_set,
    )
