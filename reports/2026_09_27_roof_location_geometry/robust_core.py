"""Pure Student-t Doppler scoring with train-only candidate selection.

The scale and degrees of freedom are explicit frozen inputs. Candidate identity
is shared across every reserve observation in a track.
"""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np


def _finite_array(name: str, value: object, ndim: int) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimensions")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be finite")
    return result


def _parameters(scale_hz: float, degrees_of_freedom: float) -> tuple[float, float]:
    scale, df = float(scale_hz), float(degrees_of_freedom)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("scale_hz must be positive and finite")
    if not math.isfinite(df) or df <= 0:
        raise ValueError("degrees_of_freedom must be positive and finite")
    return scale, df


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def student_t_logpdf(
    residual_hz: object, *, scale_hz: float, degrees_of_freedom: float,
) -> np.ndarray:
    """Normalized zero-location Student-t log density in Hz units."""
    residual = _finite_array("residual_hz", residual_hz, np.asarray(residual_hz).ndim)
    scale, df = _parameters(scale_hz, degrees_of_freedom)
    constant = (math.lgamma((df + 1.0) / 2.0) - math.lgamma(df / 2.0)
                - 0.5 * math.log(df * math.pi) - math.log(scale))
    return constant - 0.5 * (df + 1.0) * np.log1p((residual / scale) ** 2 / df)


def robust_location(
    residual_hz: object, *, scale_hz: float, degrees_of_freedom: float,
    tolerance_hz: float = 1e-8, max_iterations: int = 100,
) -> float:
    """Profile a constant CFO by deterministic Student-t IRLS."""
    residual = _finite_array("residual_hz", residual_hz, 1)
    if residual.size == 0:
        raise ValueError("at least one training residual is required")
    return float(robust_locations(
        residual[None, :], scale_hz=scale_hz,
        degrees_of_freedom=degrees_of_freedom, tolerance_hz=tolerance_hz,
        max_iterations=max_iterations,
    )[0])


def robust_locations(
    residual_hz: object, *, scale_hz: float, degrees_of_freedom: float,
    tolerance_hz: float = 1e-8, max_iterations: int = 100,
) -> np.ndarray:
    """Vectorized Student-t constant locations, one row per candidate."""
    residual = _finite_array("residual_hz", residual_hz, 2)
    if residual.shape[0] == 0 or residual.shape[1] == 0:
        raise ValueError("each candidate requires training residuals")
    scale, df = _parameters(scale_hz, degrees_of_freedom)
    if tolerance_hz <= 0 or max_iterations <= 0:
        raise ValueError("invalid robust-location iteration controls")
    location = np.median(residual, axis=1)
    active = np.ones(residual.shape[0], dtype=bool)
    for _ in range(max_iterations):
        standardized = (residual[active] - location[active, None]) / scale
        weights = (df + 1.0) / (df + standardized**2)
        updated = (np.sum(weights * residual[active], axis=1)
                   / np.sum(weights, axis=1))
        active_indices = np.flatnonzero(active)
        converged = np.abs(updated - location[active]) <= tolerance_hz
        location[active_indices] = updated
        active[active_indices[converged]] = False
        if not np.any(active):
            break
    return location


def robust_train_shortlist(
    predicted_hz: object, measured_hz: object, train_mask: object,
    visible: object, *, scale_hz: float, degrees_of_freedom: float,
    top_k: int = 3, candidate_chunk_size: int = 1024,
) -> dict[str, object]:
    """Fit CFO and rank candidates using Doppler-training observations only."""
    predicted = _finite_array("predicted_hz", predicted_hz, 2)
    measured = _finite_array("measured_hz", measured_hz, 1)
    train = np.asarray(train_mask, dtype=bool)
    visibility = np.asarray(visible, dtype=bool)
    scale, df = _parameters(scale_hz, degrees_of_freedom)
    if predicted.shape[1] != measured.size or train.shape != measured.shape:
        raise ValueError("prediction, measurement, and train-mask lengths disagree")
    if visibility.shape != (predicted.shape[0],):
        raise ValueError("visible must contain one value per candidate")
    if not np.any(train) or not np.any(~train):
        raise ValueError("both training and reserve observations are required")
    eligible = np.flatnonzero(visibility)
    if eligible.size == 0:
        raise ValueError("no visible candidates")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if candidate_chunk_size <= 0:
        raise ValueError("candidate_chunk_size must be positive")
    offsets = np.empty(predicted.shape[0])
    training_rms = np.empty(predicted.shape[0])
    train_log_likelihood = np.full(predicted.shape[0], -np.inf)
    for start in range(0, eligible.size, candidate_chunk_size):
        candidates = eligible[start:start + candidate_chunk_size]
        residual = measured[None, train] - predicted[candidates][:, train]
        locations = robust_locations(
            residual, scale_hz=scale, degrees_of_freedom=df
        )
        centered = residual - locations[:, None]
        offsets[candidates] = locations
        training_rms[candidates] = np.sqrt(np.mean(centered**2, axis=1))
        train_log_likelihood[candidates] = np.sum(student_t_logpdf(
            centered, scale_hz=scale, degrees_of_freedom=df,
        ), axis=1)
    # Stable sorting makes candidate index the fixed tie-break.
    order = eligible[np.argsort(-train_log_likelihood[eligible], kind="stable")[:top_k]]
    selected_log = train_log_likelihood[order]
    log_weights = selected_log - _logsumexp(selected_log)
    weights = np.exp(log_weights)
    return {
        "candidate_indices": order.tolist(),
        "weights": weights.tolist(),
        "log_weights": log_weights.tolist(),
        "profiled_cfo_hz": offsets[order].tolist(),
        "training_log_likelihood": selected_log.tolist(),
        "training_mean_nll": (-selected_log / int(np.sum(train))).tolist(),
        "training_rms_hz": training_rms[order].tolist(),
        "scale_hz": scale,
        "degrees_of_freedom": df,
        "training_observations": int(np.sum(train)),
    }


def train_shortlist(
    predicted_hz: object, measured_hz: object, train_mask: object,
    visible: object, *, scale_hz: float, df: float, top_k: int = 3,
) -> dict[str, object]:
    """Search-adapter spelling for :func:`robust_train_shortlist`."""
    return robust_train_shortlist(
        predicted_hz, measured_hz, train_mask, visible, scale_hz=scale_hz,
        degrees_of_freedom=df, top_k=top_k,
    )


def robust_heldout_score(
    predicted_hz: object, measured_hz: object, train_mask: object,
    shortlist: Mapping[str, object],
) -> dict[str, object]:
    """Marginalize one candidate identity shared across the whole reserve."""
    predicted = _finite_array("predicted_hz", predicted_hz, 2)
    measured = _finite_array("measured_hz", measured_hz, 1)
    train = np.asarray(train_mask, dtype=bool)
    if predicted.shape[1] != measured.size or train.shape != measured.shape:
        raise ValueError("prediction, measurement, and mask lengths disagree")
    reserve = np.flatnonzero(~train)
    if reserve.size == 0:
        raise ValueError("no reserve observations")
    indices = np.asarray(shortlist["candidate_indices"], dtype=int)
    offsets = _finite_array("profiled_cfo_hz", shortlist["profiled_cfo_hz"], 1)
    log_weights = _finite_array("log_weights", shortlist["log_weights"], 1)
    scale, df = _parameters(shortlist["scale_hz"], shortlist["degrees_of_freedom"])
    if indices.ndim != 1 or not indices.size or not (indices.size == offsets.size == log_weights.size):
        raise ValueError("invalid shortlist dimensions")
    if np.any(indices < 0) or np.any(indices >= predicted.shape[0]) or len(set(indices.tolist())) != indices.size:
        raise ValueError("invalid shortlist candidate indices")
    if not np.isclose(_logsumexp(log_weights), 0.0, atol=1e-10):
        raise ValueError("shortlist log_weights must be normalized")
    residual = measured[reserve][None, :] - (predicted[indices][:, reserve] + offsets[:, None])
    component_log_likelihood = np.sum(student_t_logpdf(
        residual, scale_hz=scale, degrees_of_freedom=df,
    ), axis=1)
    track_log_likelihood = _logsumexp(log_weights + component_log_likelihood)
    posterior_log_weights = log_weights + component_log_likelihood - track_log_likelihood
    map_position = int(np.argmax(posterior_log_weights))
    return {
        "mean_nll": float(-track_log_likelihood / reserve.size),
        "observations": int(reserve.size),
        "candidate_reserve_log_likelihood": component_log_likelihood.tolist(),
        "posterior_log_weights": posterior_log_weights.tolist(),
        "map_candidate_index": int(indices[map_position]),
        "map_reserve_rms_hz": float(np.sqrt(np.mean(residual[map_position] ** 2))),
        "identity_model": "one candidate shared across all reserve observations",
    }


def robust_doppler_track_score(
    predicted_hz: object, measured_hz: object, train_mask: object,
    visible: object, *, scale_hz: float, degrees_of_freedom: float,
    top_k: int = 3,
) -> dict[str, object]:
    """Integration interface returning shortlist and robust reserve score."""
    shortlist = robust_train_shortlist(
        predicted_hz, measured_hz, train_mask, visible,
        scale_hz=scale_hz, degrees_of_freedom=degrees_of_freedom, top_k=top_k,
    )
    reserve = robust_heldout_score(predicted_hz, measured_hz, train_mask, shortlist)
    return {"score": reserve["mean_nll"], "shortlist": shortlist, "reserve": reserve}


def joint_heldout_score(
    predicted_hz: object, candidate_east: object, measured_hz: object,
    train_mask: object, shortlist: Mapping[str, object],
    reception_rows: list[Mapping[str, object]], *, ratio_variance: float,
) -> dict[str, object]:
    """Marginalize one track-wide identity after adding candidate RX evidence."""
    predicted = _finite_array("predicted_hz", predicted_hz, 2)
    east = _finite_array("candidate_east", candidate_east, 2)
    measured = _finite_array("measured_hz", measured_hz, 1)
    train = np.asarray(train_mask, dtype=bool)
    if predicted.shape != east.shape or predicted.shape[1] != measured.size or train.shape != measured.shape:
        raise ValueError("prediction, east, measurement, and mask shapes disagree")
    reserve = np.flatnonzero(~train)
    if reserve.size == 0:
        raise ValueError("no reserve observations")
    indices = np.asarray(shortlist["candidate_indices"], dtype=int)
    offsets = _finite_array("profiled_cfo_hz", shortlist["profiled_cfo_hz"], 1)
    log_weights = _finite_array("log_weights", shortlist["log_weights"], 1)
    scale, df = _parameters(shortlist["scale_hz"], shortlist["degrees_of_freedom"])
    if indices.ndim != 1 or not indices.size or not (indices.size == offsets.size == log_weights.size):
        raise ValueError("invalid shortlist dimensions")
    if np.any(indices < 0) or np.any(indices >= predicted.shape[0]):
        raise ValueError("invalid shortlist candidate indices")
    if not np.isclose(_logsumexp(log_weights), 0.0, atol=1e-10):
        raise ValueError("shortlist log_weights must be normalized")
    if not math.isfinite(ratio_variance) or ratio_variance <= 0:
        raise ValueError("ratio_variance must be positive and finite")

    residual = measured[reserve][None, :] - (predicted[indices][:, reserve] + offsets[:, None])
    frequency_ll = np.sum(student_t_logpdf(
        residual, scale_hz=scale, degrees_of_freedom=df,
    ), axis=1)
    detection_ll = np.zeros(indices.size)
    ratio_ll = np.zeros(indices.size)
    reverse_detection_ll = np.zeros(indices.size)
    reverse_ratio_ll = np.zeros(indices.size)
    matched_count = 0
    for row in reception_rows:
        observation = int(row["observation_index"])
        if observation < 0 or observation >= measured.size or train[observation]:
            raise ValueError("reception rows must reference reserve observations")
        matched = row["matched"]
        if not isinstance(matched, (bool, np.bool_)):
            raise ValueError("matched must be boolean")
        candidate_x = east[indices, observation]
        intercept = float(row["detection_logit_east0"])
        slope = float(row["detection_east_slope"])
        logits = intercept + slope * candidate_x
        reverse_logits = intercept - slope * candidate_x
        # log P(y|candidate), evaluated stably.
        detection_ll -= np.logaddexp(0.0, -logits if matched else logits)
        reverse_detection_ll -= np.logaddexp(0.0, -reverse_logits if matched else reverse_logits)
        if matched:
            observed = row.get("log_margin_ratio_rx1_rx0")
            if observed is None or not math.isfinite(float(observed)):
                raise ValueError("matched rows require a finite log margin ratio")
            ratio_intercept = float(row["ratio_mean_east0"])
            ratio_slope = float(row["ratio_east_slope"])
            normal_constant = -0.5 * (math.log(2.0 * math.pi) + math.log(ratio_variance))
            ratio_ll += normal_constant - 0.5 * (
                (float(observed) - (ratio_intercept + ratio_slope * candidate_x)) ** 2
                / ratio_variance
            )
            reverse_ratio_ll += normal_constant - 0.5 * (
                (float(observed) - (ratio_intercept - ratio_slope * candidate_x)) ** 2
                / ratio_variance
            )
            matched_count += 1

    def score(extra: np.ndarray) -> float:
        return float(-_logsumexp(log_weights + frequency_ll + extra) / reserve.size)

    zero = np.zeros(indices.size)
    scores = {
        "D": score(zero),
        "D_plus_detection": score(detection_ll),
        "D_plus_geometry": score(detection_ll + ratio_ll),
        "D_plus_reversed_geometry": score(reverse_detection_ll + reverse_ratio_ll),
    }
    frequency_posterior = log_weights + frequency_ll
    map_position = int(np.argmax(frequency_posterior))
    return {
        "scores": scores,
        "reserve_observations": int(reserve.size),
        "reception_observations": len(reception_rows),
        "matched_reception_observations": matched_count,
        "candidate_frequency_log_likelihood": frequency_ll.tolist(),
        "candidate_detection_log_likelihood": detection_ll.tolist(),
        "candidate_ratio_log_likelihood": ratio_ll.tolist(),
        "map_candidate_index": int(indices[map_position]),
        "map_heldout_rms_hz": float(np.sqrt(np.mean(residual[map_position] ** 2))),
        "identity_model": "one candidate shared across all frequency and reception evidence in the track",
    }
