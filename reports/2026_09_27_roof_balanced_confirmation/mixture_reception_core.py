"""Pure shared-identity reception-mixture likelihood and optimizer utilities."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np


# Frozen before any real calibration fit. These apply identically to M0,
# mean-direction M1, mixture M1, and every conditional-LOSO fold.
DEFAULT_START_COEFFICIENT = .2
DEFAULT_START_LOG_SIGMA = .25
DEFAULT_GRADIENT_TOLERANCE = 1e-6
DEFAULT_OBJECTIVE_STABILITY_TOLERANCE = 1e-7
DEFAULT_PREDICTION_STABILITY_TOLERANCE = 1e-4
DEFAULT_CURVATURE_TOLERANCE = 1e-7


@dataclass(frozen=True)
class TrackData:
    log_weights: object
    detection_design: object
    matched: object
    ratio_design: object
    log_ratio: object


@dataclass(frozen=True)
class ParameterLayout:
    detection_size: int
    ratio_size: int
    detection_penalty_mask: object
    ratio_penalty_mask: object

    @property
    def size(self) -> int:
        return self.detection_size + self.ratio_size + 1


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + math.log(float(np.sum(np.exp(values - maximum))))


def _softmax_log(values: np.ndarray) -> np.ndarray:
    return np.exp(values - _logsumexp(values))


def _layout(layout: ParameterLayout) -> tuple[np.ndarray, np.ndarray]:
    if layout.detection_size <= 0 or layout.ratio_size <= 0:
        raise ValueError("both parameter blocks must be nonempty")
    detection = np.asarray(layout.detection_penalty_mask, dtype=bool)
    ratio = np.asarray(layout.ratio_penalty_mask, dtype=bool)
    if detection.shape != (layout.detection_size,) or ratio.shape != (layout.ratio_size,):
        raise ValueError("penalty masks disagree with parameter sizes")
    return detection, ratio


def _track(track: TrackData, layout: ParameterLayout) -> tuple[np.ndarray, ...]:
    log_weights = np.asarray(track.log_weights, dtype=float)
    detection = np.asarray(track.detection_design, dtype=float)
    matched = np.asarray(track.matched, dtype=bool)
    ratio = np.asarray(track.ratio_design, dtype=float)
    observed = np.asarray(track.log_ratio, dtype=float)
    if log_weights.ndim != 1 or not len(log_weights):
        raise ValueError("log_weights must be a nonempty vector")
    if detection.ndim != 3 or detection.shape[0] != len(log_weights):
        raise ValueError("detection design must have shape candidate,row,feature")
    candidates, rows, features = detection.shape
    if features != layout.detection_size:
        raise ValueError("detection feature count disagrees with layout")
    if ratio.shape != (candidates, rows, layout.ratio_size):
        raise ValueError("ratio design shape disagrees with detection/layout")
    if matched.shape != (rows,) or observed.shape != (rows,) or rows == 0:
        raise ValueError("outcomes must be nonempty row vectors")
    if not all(np.all(np.isfinite(value)) for value in
               (log_weights, detection, ratio)):
        raise ValueError("weights and designs must be finite")
    if not np.all(np.isfinite(observed[matched])):
        raise ValueError("matched ratios must be finite")
    if not np.isclose(_logsumexp(log_weights), 0., rtol=0, atol=1e-10):
        raise ValueError("log_weights must be normalized")
    return log_weights, detection, matched, ratio, observed


def objective_gradient(theta: object, tracks: Sequence[TrackData],
                       layout: ParameterLayout, ridge: float = 1.0,
                       *, return_details: bool = False):
    """Return penalized negative log likelihood and analytic gradient.

    One candidate identity is shared by every row of a track. Each track's
    marginalized log likelihood is divided by its full reception-row count.
    """
    detection_mask, ratio_mask = _layout(layout)
    parameter = np.asarray(theta, dtype=float)
    if parameter.shape != (layout.size,) or not np.all(np.isfinite(parameter)):
        raise ValueError("theta has invalid shape or values")
    if not tracks:
        raise ValueError("at least one track is required")
    if not math.isfinite(ridge) or ridge < 0:
        raise ValueError("ridge must be finite and nonnegative")
    pd = layout.detection_size
    pr = layout.ratio_size
    beta_d = parameter[:pd]
    beta_r = parameter[pd:pd + pr]
    log_sigma = float(parameter[-1])
    inverse_variance = math.exp(-2. * log_sigma)
    normal_constant = -.5 * math.log(2. * math.pi) - log_sigma
    objective = 0.
    gradient = np.zeros_like(parameter)
    details = []
    for raw in tracks:
        log_weights, design_d, matched, design_r, observed = _track(raw, layout)
        logits = np.einsum("knp,p->kn", design_d, beta_d)
        probability = 1. / (1. + np.exp(-np.clip(logits, -40., 40.)))
        # Stable Bernoulli log likelihood.
        y = matched.astype(float)
        detection_ll = np.sum(y[None, :] * logits - np.logaddexp(0., logits), axis=1)
        detection_gradient = np.einsum(
            "knp,kn->kp", design_d, y[None, :] - probability)

        ratio_ll = np.zeros(len(log_weights))
        ratio_gradient = np.zeros((len(log_weights), pr))
        sigma_gradient = np.zeros(len(log_weights))
        if np.any(matched):
            selected_design = design_r[:, matched, :]
            mean = np.einsum("kmp,p->km", selected_design, beta_r)
            residual = observed[matched][None, :] - mean
            ratio_ll = np.sum(
                normal_constant - .5 * residual**2 * inverse_variance, axis=1)
            ratio_gradient = np.einsum(
                "kmp,km->kp", selected_design, residual * inverse_variance)
            sigma_gradient = np.sum(-1. + residual**2 * inverse_variance, axis=1)

        component = detection_ll + ratio_ll
        posterior = _softmax_log(log_weights + component)
        rows = matched.size
        track_nll = -_logsumexp(log_weights + component) / rows
        objective += track_nll
        gradient[:pd] -= posterior @ detection_gradient / rows
        gradient[pd:pd + pr] -= posterior @ ratio_gradient / rows
        gradient[-1] -= posterior @ sigma_gradient / rows
        if return_details:
            details.append({
                "rows": int(rows), "matched_rows": int(np.count_nonzero(matched)),
                "component_log_likelihood": component.tolist(),
                "posterior_weights": posterior.tolist(),
                "negative_log_likelihood": float(track_nll),
            })

    penalty_d = beta_d * detection_mask
    penalty_r = beta_r * ratio_mask
    objective += .5 * ridge * (float(penalty_d @ penalty_d) +
                               float(penalty_r @ penalty_r))
    gradient[:pd] += ridge * penalty_d
    gradient[pd:pd + pr] += ridge * penalty_r
    if not math.isfinite(objective) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("objective or gradient is nonfinite")
    if return_details:
        return float(objective), gradient, details
    return float(objective), gradient


def candidate_free_objective_gradient(theta: object,
                                      tracks: Sequence[TrackData],
                                      layout: ParameterLayout,
                                      ridge: float = 1.0):
    """Independent same-objective oracle for candidate-invariant designs."""
    detection_mask, ratio_mask = _layout(layout)
    parameter = np.asarray(theta, dtype=float)
    if parameter.shape != (layout.size,) or not np.all(np.isfinite(parameter)):
        raise ValueError("theta has invalid shape or values")
    if not tracks or not math.isfinite(ridge) or ridge < 0:
        raise ValueError("invalid tracks or ridge")
    pd, pr = layout.detection_size, layout.ratio_size
    beta_d = parameter[:pd]
    beta_r = parameter[pd:pd + pr]
    log_sigma = float(parameter[-1])
    inverse_variance = math.exp(-2. * log_sigma)
    normal_constant = -.5 * math.log(2. * math.pi) - log_sigma
    objective = 0.
    gradient = np.zeros_like(parameter)
    for raw in tracks:
        log_weights, detection, matched, ratio, observed = _track(raw, layout)
        del log_weights
        if (not np.allclose(detection, detection[:1], rtol=0, atol=1e-12) or
                not np.allclose(ratio, ratio[:1], rtol=0, atol=1e-12)):
            raise ValueError("candidate-free oracle requires invariant designs")
        x_d = detection[0]
        logits = x_d @ beta_d
        probability = 1. / (1. + np.exp(-np.clip(logits, -40., 40.)))
        y = matched.astype(float)
        log_likelihood = float(np.sum(
            y * logits - np.logaddexp(0., logits)))
        gradient_d = x_d.T @ (y - probability)
        gradient_r = np.zeros(pr)
        gradient_sigma = 0.
        if np.any(matched):
            x_r = ratio[0, matched]
            residual = observed[matched] - x_r @ beta_r
            log_likelihood += float(np.sum(
                normal_constant - .5 * residual**2 * inverse_variance))
            gradient_r = x_r.T @ (residual * inverse_variance)
            gradient_sigma = float(np.sum(-1. + residual**2 * inverse_variance))
        rows = matched.size
        objective -= log_likelihood / rows
        gradient[:pd] -= gradient_d / rows
        gradient[pd:pd + pr] -= gradient_r / rows
        gradient[-1] -= gradient_sigma / rows
    penalty_d = beta_d * detection_mask
    penalty_r = beta_r * ratio_mask
    objective += .5 * ridge * (float(penalty_d @ penalty_d) +
                               float(penalty_r @ penalty_r))
    gradient[:pd] += ridge * penalty_d
    gradient[pd:pd + pr] += ridge * penalty_r
    if not math.isfinite(objective) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("candidate-free objective or gradient is nonfinite")
    return float(objective), gradient


def score_tracks(theta: object, tracks: Sequence[TrackData],
                 layout: ParameterLayout) -> list[dict[str, float]]:
    """Unpenalized shared-identity held-track component decomposition."""
    parameter = np.asarray(theta, dtype=float)
    if parameter.shape != (layout.size,) or not np.all(np.isfinite(parameter)):
        raise ValueError("theta has invalid shape or values")
    pd, pr = layout.detection_size, layout.ratio_size
    beta_d = parameter[:pd]
    beta_r = parameter[pd:pd + pr]
    log_sigma = float(parameter[-1])
    inverse_variance = math.exp(-2. * log_sigma)
    normal_constant = -.5 * math.log(2. * math.pi) - log_sigma
    result = []
    for raw in tracks:
        log_weights, design_d, matched, design_r, observed = _track(raw, layout)
        logits = np.einsum("knp,p->kn", design_d, beta_d)
        y = matched.astype(float)
        detection_ll = np.sum(
            y[None, :] * logits - np.logaddexp(0., logits), axis=1)
        ratio_ll = np.zeros(len(log_weights))
        if np.any(matched):
            mean = np.einsum("kmp,p->km", design_r[:, matched, :], beta_r)
            residual = observed[matched][None, :] - mean
            ratio_ll = np.sum(
                normal_constant - .5 * residual**2 * inverse_variance, axis=1)
        denominator = matched.size
        detection_nll = -_logsumexp(log_weights + detection_ll) / denominator
        joint_nll = -_logsumexp(
            log_weights + detection_ll + ratio_ll) / denominator
        result.append({
            "rows": int(denominator),
            "matched_rows": int(np.count_nonzero(matched)),
            "detection_marginal_nll": float(detection_nll),
            "conditional_ratio_increment_nll": float(joint_nll - detection_nll),
            "joint_nll": float(joint_nll),
        })
    return result


def finite_difference_gradient(theta: object, tracks: Sequence[TrackData],
                               layout: ParameterLayout, ridge: float = 1.0,
                               step: float = 1e-6) -> np.ndarray:
    parameter = np.asarray(theta, dtype=float)
    result = np.empty_like(parameter)
    for index in range(parameter.size):
        delta = np.zeros_like(parameter)
        delta[index] = step
        plus = objective_gradient(parameter + delta, tracks, layout, ridge)[0]
        minus = objective_gradient(parameter - delta, tracks, layout, ridge)[0]
        result[index] = (plus - minus) / (2. * step)
    return result


def numerical_hessian(theta: object, tracks: Sequence[TrackData],
                      layout: ParameterLayout, ridge: float = 1.0,
                      step: float = 1e-5) -> np.ndarray:
    parameter = np.asarray(theta, dtype=float)
    result = np.empty((parameter.size, parameter.size))
    for index in range(parameter.size):
        delta = np.zeros_like(parameter)
        delta[index] = step
        plus = objective_gradient(parameter + delta, tracks, layout, ridge)[1]
        minus = objective_gradient(parameter - delta, tracks, layout, ridge)[1]
        result[:, index] = (plus - minus) / (2. * step)
    return (result + result.T) / 2.


def default_starts(layout: ParameterLayout) -> list[np.ndarray]:
    """Three predeclared standardized starts shared by every arm and fold."""
    _layout(layout)
    zero = np.zeros(layout.size)
    positive = np.full(layout.size, DEFAULT_START_COEFFICIENT)
    negative = np.full(layout.size, -DEFAULT_START_COEFFICIENT)
    positive[-1] = DEFAULT_START_LOG_SIGMA
    negative[-1] = -DEFAULT_START_LOG_SIGMA
    return [zero, positive, negative]


def prediction_vector(theta: object, tracks: Sequence[TrackData],
                      layout: ParameterLayout) -> np.ndarray:
    """Fixed-prior mean probabilities/ratio means for start-stability checks."""
    parameter = np.asarray(theta, dtype=float)
    if parameter.shape != (layout.size,):
        raise ValueError("theta shape disagrees with layout")
    pd, pr = layout.detection_size, layout.ratio_size
    values = []
    for raw in tracks:
        log_weights, detection, _matched, ratio, _observed = _track(raw, layout)
        weights = np.exp(log_weights)
        logits = np.einsum("knp,p->kn", detection, parameter[:pd])
        probability = 1. / (1. + np.exp(-np.clip(logits, -40., 40.)))
        means = np.einsum("knp,p->kn", ratio, parameter[pd:pd + pr])
        values.extend((weights @ probability).tolist())
        values.extend((weights @ means).tolist())
        values.append(float(parameter[-1]))
    result = np.asarray(values, float)
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("prediction vector is nonfinite")
    return result


def objective_stability(objectives: object, track_count: int,
                        tolerance: float = DEFAULT_OBJECTIVE_STABILITY_TOLERANCE,
                        ) -> tuple[bool, float, float]:
    """Gate on total penalized objective spread; per-track is diagnostic only."""
    values = np.asarray(objectives, dtype=float)
    if (values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)) or
            track_count <= 0 or not math.isfinite(tolerance) or tolerance < 0):
        raise ValueError("invalid objective stability inputs")
    total_range = float(np.max(values) - np.min(values))
    return total_range <= tolerance, total_range, total_range / track_count


def optimize_multistart(tracks: Sequence[TrackData], layout: ParameterLayout,
                        ridge: float = 1.0, starts: Sequence[object] | None = None,
                        *, gradient_tolerance: float = DEFAULT_GRADIENT_TOLERANCE,
                        stability_tolerance: float = DEFAULT_OBJECTIVE_STABILITY_TOLERANCE,
                        prediction_stability_tolerance: float = DEFAULT_PREDICTION_STABILITY_TOLERANCE) -> dict[str, object]:
    """Optimize from deterministic starts and report stability/curvature."""
    from scipy.optimize import minimize

    initial = list(starts) if starts is not None else default_starts(layout)
    if len(initial) < 2:
        raise ValueError("multistart optimization requires at least two starts")
    runs = []
    for start in initial:
        value = np.asarray(start, dtype=float)
        if value.shape != (layout.size,) or not np.all(np.isfinite(value)):
            raise ValueError("invalid optimizer start")
        result = minimize(
            lambda x: objective_gradient(x, tracks, layout, ridge), value,
            jac=True, method="L-BFGS-B",
            options={"ftol": 1e-13, "gtol": 1e-9, "maxiter": 2000})
        objective, gradient = objective_gradient(result.x, tracks, layout, ridge)
        runs.append({
            "theta": result.x.tolist(), "objective": objective,
            "gradient_max_abs": float(np.max(np.abs(gradient))),
            "optimizer_success": bool(result.success),
            "optimizer_status": int(result.status), "optimizer_message": str(result.message),
            "iterations": int(result.nit),
        })
    best_index = min(range(len(runs)), key=lambda index: runs[index]["objective"])
    best = runs[best_index]
    objectives = np.asarray([run["objective"] for run in runs])
    stable, objective_range, objective_per_track_range = objective_stability(
        objectives, len(tracks), stability_tolerance)
    gradients_ok = all(run["gradient_max_abs"] <= gradient_tolerance for run in runs)
    optimizer_ok = all(run["optimizer_success"] for run in runs)
    hessian = numerical_hessian(best["theta"], tracks, layout, ridge)
    eigenvalues = np.linalg.eigvalsh(hessian)
    curvature_tolerance = DEFAULT_CURVATURE_TOLERANCE
    predictions = [prediction_vector(run["theta"], tracks, layout) for run in runs]
    best_prediction = predictions[best_index]
    prediction_difference = max(float(np.max(np.abs(value - best_prediction)))
                                for value in predictions)
    predictions_stable = prediction_difference <= prediction_stability_tolerance
    numerical_failures = []
    if not optimizer_ok:
        numerical_failures.append("one_or_more_optimizer_runs_reported_failure")
    if not gradients_ok:
        numerical_failures.append("one_or_more_gradient_norms_exceed_threshold")
    identifiability_concerns = []
    # Start disagreement/curvature are substantive only after the numerical
    # convergence gates pass; otherwise they are uninterpretable diagnostics.
    if not numerical_failures:
        if not stable:
            identifiability_concerns.append("multistart_objectives_disagree")
        if not predictions_stable:
            identifiability_concerns.append("multistart_predictions_disagree")
        if eigenvalues[0] <= curvature_tolerance:
            identifiability_concerns.append("near_zero_or_negative_local_curvature")
    return {
        "theta": best["theta"], "objective": best["objective"],
        "best_start_index": best_index, "runs": runs,
        "objective_range": objective_range,
        "objective_per_track_range": objective_per_track_range,
        "stable_objective": stable, "all_gradients_within_tolerance": gradients_ok,
        "all_optimizer_success": optimizer_ok,
        "gradient_tolerance": gradient_tolerance,
        "stability_tolerance": stability_tolerance,
        "prediction_max_absolute_difference": prediction_difference,
        "prediction_stability_tolerance": prediction_stability_tolerance,
        "stable_predictions": bool(predictions_stable),
        "curvature": {
            "minimum_eigenvalue": float(eigenvalues[0]),
            "maximum_eigenvalue": float(eigenvalues[-1]),
            "near_zero_or_negative_eigenvalues": int(np.count_nonzero(
                eigenvalues <= curvature_tolerance)),
            "tolerance": curvature_tolerance,
            "identifiable": bool(eigenvalues[0] > curvature_tolerance),
        },
        "failure_reasons": {
            "numerical_inconclusive": numerical_failures,
            "identifiability_concerns": identifiability_concerns,
        },
        "accepted": bool(stable and predictions_stable and gradients_ok and optimizer_ok and
                         eigenvalues[0] > curvature_tolerance),
    }
