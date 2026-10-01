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


@dataclass(frozen=True)
class _CompactBranch:
    observation: np.ndarray
    probability: float
    mean: np.ndarray
    jacobian: np.ndarray
    columns: np.ndarray
    covariance: np.ndarray


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


def _scatter_normal_contribution(
    system: np.ndarray,
    gradient: np.ndarray,
    active_lookup: np.ndarray,
    jacobian: np.ndarray,
    covariance: np.ndarray,
    residual: np.ndarray,
    weight: float,
    global_columns: np.ndarray | None = None,
) -> None:
    """Add one exact branch contribution using only nonzero Jacobian columns."""
    if global_columns is None:
        global_columns = np.flatnonzero(np.any(jacobian != 0.0, axis=0))
        local_h = jacobian[:, global_columns]
    else:
        global_columns = np.asarray(global_columns, dtype=int)
        local_h = jacobian
        if local_h.shape[1] != global_columns.size:
            raise ValueError("local Jacobian columns do not match global column indices")
    if global_columns.size == 0 or weight == 0.0:
        return
    positions = active_lookup[global_columns]
    if np.any(positions < 0):
        raise ValueError("active-coordinate lookup omits a nonzero Jacobian column")
    # One covariance factorization/solve supplies both the residual and design
    # results.  The scatter is algebraically identical to a full-width H.T R^-1 H.
    solved = np.linalg.solve(covariance, np.column_stack((residual, local_h)))
    solved_residual = solved[:, 0]
    solved_h = solved[:, 1:]
    system[np.ix_(positions, positions)] += weight * local_h.T @ solved_h
    gradient[positions] += weight * local_h.T @ solved_residual


def _scatter_student_t_contribution(
    system: np.ndarray,
    gradient: np.ndarray,
    active_lookup: np.ndarray,
    branch: _CompactBranch,
    degrees_of_freedom: float,
) -> None:
    """Add one compact responsibility-weighted Student-t normal contribution."""
    if branch.columns.size == 0 or branch.probability == 0.0:
        return
    positions = active_lookup[branch.columns]
    if np.any(positions < 0):
        raise ValueError("active-coordinate lookup omits a compact Jacobian column")
    residual = branch.observation - branch.mean
    solved = np.linalg.solve(
        branch.covariance, np.column_stack((residual, branch.jacobian))
    )
    solved_residual = solved[:, 0]
    weight = branch.probability * student_t_weight(
        float(residual @ solved_residual), residual.size, degrees_of_freedom
    )
    solved_h = solved[:, 1:]
    system[np.ix_(positions, positions)] += weight * branch.jacobian.T @ solved_h
    gradient[positions] += weight * branch.jacobian.T @ solved_residual


def _compact_linearizations(
    port: SoftFactorPort,
    state: np.ndarray,
    indices: np.ndarray,
    probabilities: np.ndarray,
) -> tuple[_CompactBranch, ...]:
    """Return compact candidate linearizations, using an optional bulk port."""
    observation = np.asarray(port.observation, dtype=float)
    bulk_method = getattr(port, "linearize_candidates", None)
    if callable(bulk_method):
        batch = bulk_method(state, indices)
        required = {"indices", "means", "jacobians", "columns", "covariance", "eligible"}
        if not isinstance(batch, dict) or set(batch) != required:
            raise ValueError("linearize_candidates returned an invalid mapping")
        returned_indices = np.asarray(batch["indices"], dtype=np.int64)
        means = np.asarray(batch["means"], dtype=float)
        jacobians = np.asarray(batch["jacobians"], dtype=float)
        columns = np.asarray(batch["columns"], dtype=np.int64)
        covariance = np.asarray(batch["covariance"], dtype=float)
        eligible = np.asarray(batch["eligible"], dtype=bool)
        count = indices.size
        if (
            returned_indices.shape != (count,)
            or not np.array_equal(returned_indices, indices)
            or means.shape != (count, observation.size)
            or jacobians.ndim != 3
            or jacobians.shape[:2] != (count, observation.size)
            or columns.shape != (count, jacobians.shape[2])
            or covariance.shape != (observation.size, observation.size)
            or eligible.shape != (count,)
            or np.any(~np.isfinite(means))
            or np.any(~np.isfinite(jacobians))
            or np.any(~np.isfinite(covariance))
            or not np.allclose(covariance, covariance.T, rtol=1e-10, atol=1e-12)
            or np.any(columns < 0)
            or np.any(columns >= state.size)
        ):
            raise ValueError("linearize_candidates returned incompatible arrays")
        try:
            np.linalg.cholesky(covariance)
        except np.linalg.LinAlgError as error:
            raise ValueError("linearize_candidates covariance must be positive definite") from error
        compact = []
        for row, index in enumerate(indices):
            if np.unique(columns[row]).size != columns.shape[1]:
                raise ValueError("linearize_candidates columns must be unique per branch")
            if not eligible[row]:
                if probabilities[index] > 1e-15:
                    raise ValueError("ineligible branch has positive responsibility")
                continue
            nonzero = np.any(jacobians[row] != 0.0, axis=0)
            compact.append(
                _CompactBranch(
                    observation,
                    float(probabilities[index]),
                    means[row],
                    jacobians[row][:, nonzero],
                    columns[row, nonzero],
                    covariance,
                )
            )
        return tuple(compact)

    compact = []
    for index in indices:
        prediction = port.predict_selected(state, int(index))
        if not prediction.eligible:
            if probabilities[index] > 1e-15:
                raise ValueError("ineligible branch has positive responsibility")
            continue
        mean = np.asarray(prediction.mean, dtype=float)
        full_jacobian = np.asarray(prediction.jacobian, dtype=float)
        covariance = np.asarray(prediction.covariance, dtype=float)
        if (
            mean.shape != observation.shape
            or full_jacobian.shape != (observation.size, state.size)
            or covariance.shape != (observation.size, observation.size)
        ):
            raise ValueError("prediction has incompatible dimensions")
        columns = np.flatnonzero(np.any(full_jacobian != 0.0, axis=0))
        compact.append(
            _CompactBranch(
                observation,
                float(probabilities[index]),
                mean,
                full_jacobian[:, columns],
                columns,
                covariance,
            )
        )
    return tuple(compact)


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

        branches: list[_CompactBranch] = []
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
                new_branches = _compact_linearizations(port, x, indices, probability)
                for branch in new_branches:
                    active_coordinates.update(map(int, branch.columns))
                branches.extend(new_branches)
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
        active_lookup = np.full(x.size, -1, dtype=int)
        active_lookup[active] = np.arange(active.size)
        system = np.diag(precision[active])
        gradient = -precision[active] * (x[active] - center[active])
        try:
            for branch in branches:
                _check_deadline(deadline)
                _scatter_student_t_contribution(
                    system, gradient, active_lookup, branch, degrees_of_freedom
                )
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
        finalized: list[np.ndarray] = []
        try:
            for port in ports:
                _check_deadline(deadline)
                finalized.append(_responsibilities(_scores(port, x)))
            final_responsibilities = tuple(finalized)
        except _DeadlineReached:
            final_responsibilities = None
            converged = False
            reason = "wall_budget"
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
