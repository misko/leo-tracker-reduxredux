"""Full soft-association IRLS with batched branches and a small shared solve.

The observation port supplies all normalized branch scores and six-column
linearizations (five shared coordinates and one satellite epoch). This is a
local optimizer, not calibrated posterior inference. No probability truncation.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Protocol

import numpy as np

from leo.analysis.localization_linear import (
    solve_diagonal_nuisance,
    student_t_branch_quadratics,
)
from leo.analysis.localization_soft import JointSoftResult


class BatchedTrackPort(Protocol):
    observation_ids: Sequence[str]
    observation: np.ndarray
    candidate_count: int
    priors_piecewise_constant: bool

    def score_all(self, state: np.ndarray) -> np.ndarray: ...

    def linearize_candidates(self, state: np.ndarray, indices: np.ndarray) -> dict: ...


def fit_batched_soft(
    initial: np.ndarray,
    factors: Sequence[BatchedTrackPort],
    prior_precision: np.ndarray,
    support: Callable[[np.ndarray], bool],
    *,
    max_iterations: int = 24,
    max_spatial_step: float = 25.,
    deadline: float | None = None,
    prior_mean: np.ndarray | None = None,
    degrees_of_freedom: float = 4.,
) -> JointSoftResult:
    """Preserve the full soft objective and original stopping thresholds.

    Requires independent, positively regularized satellite epochs. Failure of
    the positive-definite shared solve is explicit, never hidden by damping
    or a changed prior. All calls must be externally bounded by the caller;
    deadline checks cannot interrupt an individual port evaluation.
    """
    x = np.array(initial, dtype=float, copy=True)
    precision = np.asarray(prior_precision, dtype=float)
    center = np.zeros_like(x) if prior_mean is None else np.asarray(prior_mean, dtype=float)
    ports = tuple(factors)
    if (x.ndim != 1 or x.size < 6 or precision.shape != x.shape
            or center.shape != x.shape or not ports or max_iterations < 1
            or not np.isfinite(max_spatial_step) or max_spatial_step <= 0
            or not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0
            or any(not np.all(np.isfinite(v)) for v in (x, precision, center))
            or np.any(precision < 0) or np.any(precision[5:] <= 0) or not support(x)):
        raise ValueError("invalid state, prior, or optimizer configuration")
    ids = [identifier for port in ports for identifier in port.observation_ids]
    if not ids or any(not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("physical observations must be nonempty and unique")
    for port in ports:
        if (port.candidate_count != x.size-5 or port.priors_piecewise_constant is not True
                or not callable(getattr(port, 'linearize_candidates', None))):
            raise ValueError("incompatible bulk observation port")

    def check_deadline():
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError

    def evaluate(state):
        check_deadline()
        if not support(state):
            return np.inf, ()
        delta = state-center
        value = .5 * np.dot(precision*delta, delta)
        responsibilities = []
        for port in ports:
            check_deadline()
            scores = np.asarray(port.score_all(state), dtype=float)
            if (scores.shape != (x.size-4,) or np.any(np.isnan(scores))
                    or np.any(np.isposinf(scores))):
                raise ValueError("invalid branch scores")
            maximum = np.max(scores)
            if not np.isfinite(maximum):
                return np.inf, ()
            unnormalized = np.exp(scores-maximum)
            total = unnormalized.sum()
            value -= maximum + np.log(total)
            responsibilities.append(unnormalized/total)
        return float(value), tuple(responsibilities)

    objectives, norms = [], []
    converged, iterations, reason = False, 0, 'iteration_limit'
    final = None
    try:
        for iteration in range(max_iterations):
            value, probabilities = evaluate(x)
            if not np.isfinite(value):
                reason = 'infeasible_soft_objective'
                break
            final = probabilities
            if not objectives:
                objectives.append(value)
            elif value > objectives[-1] + 1e-6:
                raise ValueError("inconsistent objective")
            a = np.diag(precision[:5])
            b = np.zeros((5, x.size-5))
            d = precision[5:].copy()
            rhs = -precision*(x-center)
            branch_count = 0
            for port, probability in zip(ports, probabilities, strict=True):
                check_deadline()
                indices = np.flatnonzero(probability[:-1] > 0)
                if not indices.size:
                    continue
                batch = port.linearize_candidates(x, indices)
                observation = np.asarray(port.observation, dtype=float)
                means = np.asarray(batch['means'], dtype=float)
                jacobians = np.asarray(batch['jacobians'], dtype=float)
                columns = np.asarray(batch['columns'])
                eligible = np.asarray(batch['eligible'], dtype=bool)
                expected = np.column_stack((
                    np.broadcast_to(np.arange(5), (len(indices), 5)), 5+indices,
                ))
                if (not np.array_equal(batch['indices'], indices)
                        or observation.ndim != 1 or not np.all(np.isfinite(observation))
                        or means.shape != (len(indices), observation.size)
                        or jacobians.shape != (len(indices), observation.size, 6)
                        or not np.array_equal(columns, expected)
                        or eligible.shape != (len(indices),)):
                    raise ValueError("invalid bulk linearization")
                if np.any(probability[indices[~eligible]] > 1e-15):
                    raise ValueError("ineligible branch has positive responsibility")
                kept = indices[eligible]
                matrices, gradients = student_t_branch_quadratics(
                    observation-means[eligible], jacobians[eligible],
                    batch['covariance'], probability[kept], degrees_of_freedom,
                )
                a += matrices[:, :5, :5].sum(axis=0)
                b[:, kept] += matrices[:, :5, 5].T
                d[kept] += matrices[:, 5, 5]
                rhs[:5] += gradients[:, :5].sum(axis=0)
                rhs[5+kept] += gradients[:, 5]
                branch_count += len(kept)
            if not branch_count:
                reason = 'all_background'
                break
            check_deadline()
            try:
                step = solve_diagonal_nuisance(a, b, d, rhs[:5], rhs[5:])
            except np.linalg.LinAlgError:
                reason = 'linear_solve_failed'
                break
            spatial = np.linalg.norm(step[:2])
            if spatial > max_spatial_step:
                step *= max_spatial_step/spatial
            if np.linalg.norm(step) < 1e-5:
                converged, reason = True, 'stationary'
                break
            accepted = False
            for backtrack in range(18):
                increment = step * .5**backtrack
                trial_value, trial_probabilities = evaluate(x+increment)
                if trial_value < value:
                    x += increment
                    final = trial_probabilities
                    objectives.append(trial_value)
                    norms.append(float(np.linalg.norm(increment)))
                    accepted = True
                    break
            iterations = iteration+1
            if not accepted:
                reason = 'line_search_stalled'
                break
            if value-trial_value < 1e-7 and norms[-1] < 1e-4:
                converged, reason = True, 'objective_stable'
                break
        check_deadline()
    except TimeoutError:
        final, converged, reason = None, False, 'wall_budget'
    return JointSoftResult(x, final, tuple(objectives), converged, iterations,
                           reason, tuple(norms), 0., False, final is not None, True)
