"""Pure per-track scores for reception-assisted geographic search.

Candidate selection is exclusively train-Doppler based.  Reception parameters
are frozen inputs learned elsewhere; this module never accepts position truth.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np


LOG_2PI = math.log(2.0 * math.pi)


def _array(name: str, value: object, ndim: int) -> np.ndarray:
    result = np.asarray(value)
    if result.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimensions")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be finite")
    return result


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def _logsumexp_axis0(values: np.ndarray) -> np.ndarray:
    maximum = np.max(values, axis=0)
    return maximum + np.log(np.exp(values - maximum[None, :]).sum(axis=0))


def train_shortlist(
    predicted_hz: object,
    measured_hz: object,
    train_mask: object,
    visible: object,
    *,
    sigma_hz: float = 100.0,
    top_k: int = 3,
) -> dict[str, object]:
    """Profile candidate-constant CFO on train samples and retain train top-k."""
    predicted = _array("predicted_hz", predicted_hz, 2).astype(float)
    measured = _array("measured_hz", measured_hz, 1).astype(float)
    train = np.asarray(train_mask, dtype=bool)
    visibility = np.asarray(visible, dtype=bool)
    if predicted.shape[1] != measured.size or train.shape != measured.shape:
        raise ValueError("prediction, measurement, and train-mask lengths disagree")
    if visibility.shape != (predicted.shape[0],):
        raise ValueError("visible must contain one value per candidate")
    if not np.any(train):
        raise ValueError("at least one Doppler training observation is required")
    if not np.any(~train):
        raise ValueError("at least one Doppler heldout observation is required")
    if not math.isfinite(sigma_hz) or sigma_hz <= 0:
        raise ValueError("sigma_hz must be positive and finite")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    eligible = np.flatnonzero(visibility)
    if eligible.size == 0:
        raise ValueError("no visible candidates")
    residual = measured[None, train] - predicted[:, train]
    offsets = np.mean(residual, axis=1)
    centered = residual - offsets[:, None]
    sse = np.sum(centered * centered, axis=1)
    order = eligible[np.argsort(sse[eligible], kind="stable")[:top_k]]
    log_weight = -sse[order] / (2.0 * sigma_hz**2)
    log_weight -= _logsumexp(log_weight)
    weights = np.exp(log_weight)
    return {
        "candidate_indices": order.tolist(),
        "weights": weights.tolist(),
        "log_weights": log_weight.tolist(),
        "profiled_cfo_hz": offsets[order].tolist(),
        "training_sse_hz2": sse[order].tolist(),
        "training_rms_hz": np.sqrt(sse[order] / int(np.sum(train))).tolist(),
        "sigma_hz": float(sigma_hz),
        "training_observations": int(np.sum(train)),
    }


def _shortlist_arrays(shortlist: Mapping[str, object], candidate_count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    indices = np.asarray(shortlist["candidate_indices"], dtype=int)
    weights = _array("weights", shortlist["weights"], 1).astype(float)
    offsets = _array("profiled_cfo_hz", shortlist["profiled_cfo_hz"], 1).astype(float)
    sigma = float(shortlist["sigma_hz"])
    if not (indices.ndim == 1 and indices.size and indices.size == weights.size == offsets.size):
        raise ValueError("invalid shortlist dimensions")
    if np.any(indices < 0) or np.any(indices >= candidate_count) or len(set(indices.tolist())) != indices.size:
        raise ValueError("invalid shortlist candidate indices")
    if np.any(weights < 0) or not np.any(weights > 0) or not np.isclose(np.sum(weights), 1.0, rtol=1e-10, atol=1e-12):
        raise ValueError("shortlist weights must be nonnegative and normalized")
    if "log_weights" in shortlist:
        log_weights = _array("log_weights", shortlist["log_weights"], 1).astype(float)
        if log_weights.size != weights.size or not np.isclose(_logsumexp(log_weights), 0.0, atol=1e-10):
            raise ValueError("shortlist log_weights must be normalized")
    else:
        with np.errstate(divide="ignore"):
            log_weights = np.log(weights)
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("invalid shortlist sigma")
    return indices, weights, log_weights, offsets, sigma


def doppler_heldout_score(
    predicted_hz: object,
    measured_hz: object,
    train_mask: object,
    shortlist: Mapping[str, object],
) -> dict[str, object]:
    """Mean held-out Gaussian-mixture NLL, marginalizing the fixed shortlist."""
    predicted = _array("predicted_hz", predicted_hz, 2).astype(float)
    measured = _array("measured_hz", measured_hz, 1).astype(float)
    train = np.asarray(train_mask, dtype=bool)
    if predicted.shape[1] != measured.size or train.shape != measured.shape:
        raise ValueError("prediction, measurement, and mask lengths disagree")
    heldout = np.flatnonzero(~train)
    if heldout.size == 0:
        raise ValueError("no heldout Doppler observations")
    indices, weights, log_weights, offsets, sigma = _shortlist_arrays(shortlist, predicted.shape[0])
    means = predicted[indices][:, heldout] + offsets[:, None]
    residual = measured[heldout][None, :] - means
    log_component = (log_weights[:, None] - 0.5 * (LOG_2PI + 2 * math.log(sigma))
                     - 0.5 * (residual / sigma) ** 2)
    nll = -_logsumexp_axis0(log_component)
    map_position = int(np.argmax(weights))
    map_rms = float(np.sqrt(np.mean(residual[map_position] ** 2)))
    return {
        "mean_nll": float(np.mean(nll)),
        "observations": int(heldout.size),
        "map_candidate_index": int(indices[map_position]),
        "map_heldout_rms_hz": map_rms,
    }


def reception_geometry_score(
    candidate_east: object,
    shortlist: Mapping[str, object],
    reception_rows: Sequence[Mapping[str, object]],
    *,
    ratio_variance: float,
) -> dict[str, object]:
    """Score frozen detection and conditional-ratio models at prior-mean east.

    Each row requires observation_index, matched, detection_logit_east0,
    detection_east_slope, ratio_mean_east0, and ratio_east_slope.  A matched row
    additionally requires log_margin_ratio_rx1_rx0.
    """
    east = _array("candidate_east", candidate_east, 2).astype(float)
    indices, weights, _, _, _ = _shortlist_arrays(shortlist, east.shape[0])
    if not math.isfinite(ratio_variance) or ratio_variance <= 0:
        raise ValueError("ratio_variance must be positive and finite")
    if not reception_rows:
        raise ValueError("at least one reception row is required")
    detection_losses: list[float] = []
    ratio_losses: list[float] = []
    for row in reception_rows:
        observation = int(row["observation_index"])
        if observation < 0 or observation >= east.shape[1]:
            raise ValueError("reception observation_index is out of range")
        mean_east = float(weights @ east[indices, observation])
        logit = float(row["detection_logit_east0"]) + float(row["detection_east_slope"]) * mean_east
        if not math.isfinite(logit):
            raise ValueError("non-finite frozen detection prediction")
        matched = row["matched"]
        if not isinstance(matched, (bool, np.bool_)):
            raise ValueError("matched must be boolean")
        # Stable Bernoulli negative log likelihood.
        detection_losses.append(float(np.logaddexp(0.0, -logit if matched else logit)))
        if matched:
            observed = row.get("log_margin_ratio_rx1_rx0")
            if observed is None or not math.isfinite(float(observed)):
                raise ValueError("matched rows require a finite log margin ratio")
            mean = float(row["ratio_mean_east0"]) + float(row["ratio_east_slope"]) * mean_east
            residual = float(observed) - mean
            ratio_losses.append(0.5 * (LOG_2PI + math.log(ratio_variance) + residual**2 / ratio_variance))
    matched_mean = float(np.mean(ratio_losses)) if ratio_losses else 0.0
    return {
        "detection_mean_nll": float(np.mean(detection_losses)),
        "detection_observations": len(detection_losses),
        # This is the joint-score contribution: unmatched rows add exactly zero,
        # while the denominator remains the full reception reserve.
        "conditional_ratio_mean_nll": float(np.sum(ratio_losses) / len(detection_losses)),
        "conditional_ratio_matched_only_mean_nll": matched_mean,
        "conditional_ratio_observations": len(ratio_losses),
    }


def score_track(
    predicted_hz: object,
    candidate_east: object,
    measured_hz: object,
    train_mask: object,
    visible: object,
    reception_rows: Sequence[Mapping[str, object]],
    *,
    ratio_variance: float,
    sigma_hz: float = 100.0,
    top_k: int = 3,
) -> dict[str, object]:
    """Return primary and ablation scores plus auditable shortlist diagnostics."""
    train = np.asarray(train_mask, dtype=bool)
    for row in reception_rows:
        observation = int(row["observation_index"])
        if observation < 0 or observation >= train.size:
            raise ValueError("reception observation_index is out of range")
        if train[observation]:
            raise ValueError("reception rows must use Doppler-reserve observations")
    shortlist = train_shortlist(predicted_hz, measured_hz, train_mask, visible,
                                sigma_hz=sigma_hz, top_k=top_k)
    doppler = doppler_heldout_score(predicted_hz, measured_hz, train_mask, shortlist)
    reception = reception_geometry_score(candidate_east, shortlist, reception_rows,
                                          ratio_variance=ratio_variance)
    d = float(doppler["mean_nll"])
    detection = float(reception["detection_mean_nll"])
    ratio = float(reception["conditional_ratio_mean_nll"])
    return {
        "scores": {
            "D": d,
            "D_plus_detection": d + detection,
            "D_plus_geometry": d + detection + ratio,
        },
        "shortlist": shortlist,
        "doppler": doppler,
        "reception": reception,
    }
