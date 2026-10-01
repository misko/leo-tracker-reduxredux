"""Bounded hard-association optimization with one shared nuisance prior.

This is a mode search, not a posterior integrator. Spatial proposals select
starting points only; every objective evaluates each observation exactly once.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from leo.analysis.gaussian_sum_location import ObservationFactor, gaussian_logpdf
from leo.analysis.robust_likelihood import student_t_logpdf, student_t_weight


@dataclass(frozen=True)
class JointGreedyResult:
    mean: np.ndarray
    associations: tuple[int, ...]
    objectives: tuple[float, ...]
    converged: bool
    iterations: int
    reason: str
    accepted_step_norms: tuple[float, ...]


def _prior_value(prior, state):
    return float(prior(state) if callable(prior) else prior)


def _selected_log(factor, index, state, degrees_of_freedom):
    if index == len(factor.candidates):
        prior = _prior_value(factor.background_prior, state)
        return np.log(prior) + factor.background_log_likelihood if prior > 0 else -np.inf
    candidate = factor.candidates[index]
    prior = _prior_value(candidate.prior, state)
    if prior <= 0:
        return -np.inf
    prediction = candidate.predict(state)
    if not prediction.eligible:
        return -np.inf
    residual = factor.observation - prediction.mean
    likelihood = (
        gaussian_logpdf(residual, prediction.covariance)
        if degrees_of_freedom is None
        else student_t_logpdf(residual, prediction.covariance, degrees_of_freedom)
    )
    return np.log(prior) + likelihood


def fit_joint_greedy(
    initial: np.ndarray,
    factors: Sequence[ObservationFactor],
    branch_scores: Sequence[Callable[[np.ndarray], np.ndarray]],
    prior_precision: np.ndarray,
    support: Callable[[np.ndarray], bool],
    *, max_iterations: int = 24, max_spatial_step: float = 25.,
    deadline: float | None = None, prior_mean: np.ndarray | None = None,
    degrees_of_freedom: float | None = None,
) -> JointGreedyResult:
    """Alternate exact hard association with damped joint nonlinear refitting.

The diagonal prior defaults to zero-mean; zero precision declares an improper
flat coordinate restricted by ``support``. All scoring ports must return candidate
log-joints in factor order, followed by the background log-joint.
"""
    x=np.array(initial,dtype=float,copy=True)
    precision=np.asarray(prior_precision,dtype=float)
    center = np.zeros_like(x) if prior_mean is None else np.asarray(prior_mean, dtype=float)
    if (x.ndim != 1 or precision.shape != x.shape or center.shape != x.shape
            or np.any(~np.isfinite(x)) or np.any(~np.isfinite(precision))
            or np.any(~np.isfinite(center)) or np.any(precision < 0) or not support(x)):
        raise ValueError("invalid initial state or prior")
    if max_iterations < 1 or max_spatial_step <= 0:
        raise ValueError("iteration and spatial-step limits must be positive")
    if degrees_of_freedom is not None and (
        not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0
    ):
        raise ValueError("degrees_of_freedom must be finite and positive")
    if len(factors)!=len(branch_scores) or not factors:
        raise ValueError("one scoring port is required per factor")
    ids=[identifier for factor in factors for identifier in factor.observation_ids]
    if len(ids)!=len(set(ids)):
        raise ValueError("physical observations must not be reused")
    objectives=[]
    associations=()
    reason="iteration_limit"
    converged=False
    iterations=0
    accepted_step_norms=[]

    def objective(state, assigned):
        if not support(state):
            return np.inf
        try:
            delta = state - center
            value=.5*np.dot(precision*delta,delta)
            for f,i in zip(factors,assigned,strict=True):
                value-=_selected_log(f,i,state,degrees_of_freedom)
            return float(value)
        except (ValueError,np.linalg.LinAlgError):
            return np.inf

    for iteration in range(max_iterations):
        if deadline is not None and time.monotonic() >= deadline:
            reason="wall_budget"
            break
        score_values=[]
        for factor, score in zip(factors, branch_scores, strict=True):
            values = np.asarray(score(x), dtype=float)
            if (values.shape != (len(factor.candidates) + 1,) or np.any(np.isnan(values))
                    or np.any(np.isposinf(values))):
                raise ValueError("association scorer returned invalid branch scores")
            score_values.append(values)
        assigned=tuple(int(np.argmax(values)) for values in score_values)
        for factor, index, values in zip(factors, assigned, score_values, strict=True):
            physical = _selected_log(factor, index, x, degrees_of_freedom)
            if not np.isclose(values[index], physical, rtol=1e-9, atol=1e-8):
                raise ValueError("association scorer disagrees with selected physical score")
        value=objective(x,assigned)
        if not np.isfinite(value):
            reason="infeasible_assignment"
            break
        if not objectives:
            objectives.append(value)
        elif value > objectives[-1] + 1e-6:
            raise ValueError("association scorer disagrees with physical objective")
        active={int(i) for i in np.flatnonzero(x)}
        predictions=[]
        for factor,index in zip(factors,assigned,strict=True):
            if index==len(factor.candidates):
                continue
            prediction=factor.candidates[index].predict(x)
            active.update(map(int,np.flatnonzero(np.any(prediction.jacobian != 0.,axis=0))))
            predictions.append((factor,prediction))
        stable=assigned==associations
        associations=assigned
        if not predictions:
            reason="all_background"
            break
        active=np.array(sorted(active),dtype=int)
        system=np.diag(precision[active])
        gradient=-precision[active]*(x[active]-center[active])
        for factor,prediction in predictions:
            h=prediction.jacobian[:,active]
            residual = factor.observation-prediction.mean
            solved_residual = np.linalg.solve(prediction.covariance, residual)
            weight = 1.0
            if degrees_of_freedom is not None:
                weight = student_t_weight(
                    float(residual @ solved_residual), residual.size, degrees_of_freedom
                )
            system+=weight*h.T@np.linalg.solve(prediction.covariance,h)
            gradient+=weight*h.T@solved_residual
        step=np.linalg.lstsq(system,gradient,rcond=1e-12)[0]
        spatial=[j for j,i in enumerate(active) if i in (0,1)]
        length=np.linalg.norm(step[spatial])
        if length > max_spatial_step:
            step*=max_spatial_step/length
        if stable and np.linalg.norm(step) < 1e-5:
            converged=True
            reason="stationary"
            break
        accepted=False
        for backtrack in range(18):
            trial=x.copy()
            trial[active]+=step*(.5**backtrack)
            trial_value=objective(trial,assigned)
            if trial_value < value:
                x=trial
                objectives.append(trial_value)
                accepted_step_norms.append(float(np.linalg.norm(step*(.5**backtrack))))
                accepted=True
                break
        iterations=iteration+1
        if not accepted:
            reason="line_search_stalled"
            break
        if stable and value-trial_value < 1e-7 and accepted_step_norms[-1] < 1e-4:
            converged=True
            reason="objective_stable"
            break
    return JointGreedyResult(
        x, associations, tuple(objectives), converged, iterations, reason,
        tuple(accepted_step_norms)
    )
