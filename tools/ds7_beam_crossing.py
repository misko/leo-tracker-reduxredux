#!/usr/bin/env python3
"""Pure temporal dual-receiver beam-crossing likelihood primitives.

This module does not load recordings or fit positions.  Its primary endpoint is
conditional on rows where a paired receiver response is available; callers may
only add detection/non-detection outcomes after auditing complete opportunities.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CrossingFeatures:
    """Candidate-dependent ordered receiver contrast and its changes."""

    contrast: np.ndarray
    change: np.ndarray
    crossing_time: np.ndarray
    crossing_coordinate: np.ndarray


@dataclass(frozen=True)
class ConditionalTrack:
    """One shared candidate identity and conditional paired-RX observations."""

    track_id: str
    log_weights: np.ndarray
    times: np.ndarray
    log_rx1_over_rx0: np.ndarray
    training_mask: np.ndarray
    features: CrossingFeatures
    nuisance_mean: np.ndarray | None = None


@dataclass(frozen=True)
class FeatureScale:
    """Training-only scales shared by static and temporal geometry arms."""

    contrast: float
    change: float


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    if not math.isfinite(maximum):
        return maximum
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def nominal_boresights(tilt_deg: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
    """Return provisional opposite east/west ENU boresights."""
    if not math.isfinite(tilt_deg) or not 0 < tilt_deg < 90:
        raise ValueError("tilt_deg must be finite and between zero and 90")
    angle = math.radians(tilt_deg)
    up, east = math.cos(angle), math.sin(angle)
    return np.array([-east, 0.0, up]), np.array([east, 0.0, up])


def _one_crossing_time(times: np.ndarray, contrast: np.ndarray) -> float:
    exact = np.flatnonzero(contrast == 0.0)
    changes = np.flatnonzero(contrast[:-1] * contrast[1:] < 0.0)
    candidates = [float(times[index]) for index in exact]
    for index in changes:
        left, right = float(contrast[index]), float(contrast[index + 1])
        fraction = -left / (right - left)
        candidates.append(float(times[index] + fraction * (times[index + 1] - times[index])))
    unique = []
    for value in sorted(candidates):
        if not unique or not math.isclose(value, unique[-1], rel_tol=0.0, abs_tol=1e-12):
            unique.append(value)
    return unique[0] if len(unique) == 1 else math.nan


def trajectory_features(
    times: object,
    line_of_sight_enu: object,
    receiver0_boresight: object,
    receiver1_boresight: object,
) -> CrossingFeatures:
    """Build ordered contrast/change features without inventing a crossing.

    ``line_of_sight_enu`` has shape ``(candidate, opportunity, 3)``.  A crossing
    time is finite only when exactly one zero crossing occurs inside the observed
    interval.  Candidates with zero or multiple crossings receive NaN crossing
    coordinates and must be excluded from crossing-specific claims by the caller.
    """
    t = np.asarray(times, dtype=float)
    los = np.asarray(line_of_sight_enu, dtype=float)
    b0 = np.asarray(receiver0_boresight, dtype=float)
    b1 = np.asarray(receiver1_boresight, dtype=float)
    if t.ndim != 1 or len(t) < 2 or np.any(np.diff(t) <= 0):
        raise ValueError("times must be a strictly increasing vector with at least two rows")
    if los.ndim != 3 or los.shape[1:] != (len(t), 3):
        raise ValueError("line_of_sight_enu must have shape candidate,row,3")
    if b0.shape != (3,) or b1.shape != (3,):
        raise ValueError("boresights must be three-vectors")
    if not all(np.all(np.isfinite(value)) for value in (t, los, b0, b1)):
        raise ValueError("times, directions and boresights must be finite")
    norms = np.linalg.norm(los, axis=2)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1e-7):
        raise ValueError("line-of-sight vectors must be unit length")
    contrast = np.einsum("knp,p->kn", los, b1 - b0)
    change = np.gradient(contrast, t, axis=1)
    crossing = np.array([_one_crossing_time(t, row) for row in contrast])
    duration = float(t[-1] - t[0])
    coordinate = (t[None, :] - crossing[:, None]) / duration
    return CrossingFeatures(contrast, change, crossing, coordinate)


def validate_track(track: ConditionalTrack) -> None:
    weights = np.asarray(track.log_weights, dtype=float)
    times = np.asarray(track.times, dtype=float)
    observed = np.asarray(track.log_rx1_over_rx0, dtype=float)
    mask = np.asarray(track.training_mask)
    contrast = np.asarray(track.features.contrast, dtype=float)
    change = np.asarray(track.features.change, dtype=float)
    candidates = len(weights)
    if not track.track_id or weights.ndim != 1 or candidates == 0:
        raise ValueError("track id and candidate weights are required")
    if times.ndim != 1 or len(times) < 3 or np.any(np.diff(times) <= 0):
        raise ValueError("track times must be strictly increasing with at least three rows")
    if observed.shape != times.shape or mask.shape != times.shape or mask.dtype != np.bool_:
        raise ValueError("paired response and boolean mask must match track times")
    if track.nuisance_mean is not None:
        nuisance = np.asarray(track.nuisance_mean, dtype=float)
        if nuisance.shape != times.shape or not np.all(np.isfinite(nuisance)):
            raise ValueError("nuisance mean must be a finite row vector")
    if contrast.shape != (candidates, len(times)) or change.shape != contrast.shape:
        raise ValueError("trajectory feature shape mismatch")
    values = (weights, times, observed, contrast, change)
    if not all(np.all(np.isfinite(value)) for value in values):
        raise ValueError("conditional track values must be finite")
    if not math.isclose(_logsumexp(weights), 0.0, rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("candidate log weights must be normalized")
    if len(mask) < 3:
        raise ValueError("track requires at least three rows")


def fit_feature_scale(tracks: list[ConditionalTrack]) -> FeatureScale:
    """Fit RMS scales using training rows only; held rows cannot affect them."""
    if not tracks:
        raise ValueError("at least one track is required")
    contrast, change = [], []
    for track in tracks:
        validate_track(track)
        mask = track.training_mask
        contrast.append(track.features.contrast[:, mask].ravel())
        change.append(track.features.change[:, mask].ravel())
    values = []
    for rows in (contrast, change):
        joined = np.concatenate(rows)
        scale = float(np.sqrt(np.mean(joined * joined)))
        if not math.isfinite(scale) or scale <= 1e-12:
            raise ValueError("training feature scale is degenerate")
        values.append(scale)
    return FeatureScale(*values)


def apply_feature_scale(track: ConditionalTrack, scale: FeatureScale) -> ConditionalTrack:
    """Apply a previously fitted scale without consulting held outcomes."""
    if not all(math.isfinite(value) and value > 0 for value in (scale.contrast, scale.change)):
        raise ValueError("feature scales must be finite and positive")
    features = CrossingFeatures(
        track.features.contrast / scale.contrast,
        track.features.change / scale.change,
        track.features.crossing_time.copy(),
        track.features.crossing_coordinate.copy(),
    )
    return ConditionalTrack(
        track.track_id,
        track.log_weights.copy(),
        track.times.copy(),
        track.log_rx1_over_rx0.copy(),
        track.training_mask.copy(),
        features,
        None if track.nuisance_mean is None else track.nuisance_mean.copy(),
    )


def _normal_log_density(residual: np.ndarray, log_sigma: float) -> np.ndarray:
    if not math.isfinite(log_sigma):
        raise ValueError("log sigma must be finite")
    inverse_variance = math.exp(-2.0 * log_sigma)
    return -0.5 * math.log(2.0 * math.pi) - log_sigma - 0.5 * residual**2 * inverse_variance


def component_scores(
    track: ConditionalTrack,
    parameters: object,
    *,
    temporal: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Return candidate training and held scores with strict leakage separation.

    Static parameters are ``intercept, contrast_slope, log_sigma``. Temporal
    parameters are ``intercept, contrast_slope, change_slope, log_tau_seconds,
    log_stationary_sigma``. The temporal arm is one continuous-time AR sequence likelihood;
    it does not multiply a level density by a density of the same differences.
    """
    train = selected_component_scores(track, parameters, track.training_mask, temporal=temporal)
    held = selected_component_scores(track, parameters, ~track.training_mask, temporal=temporal)
    return train, held


def selected_component_scores(
    track: ConditionalTrack,
    parameters: object,
    selected: object,
    *,
    temporal: bool,
) -> np.ndarray:
    """Score one explicit partition, including an entire held recording."""
    validate_track(track)
    theta = np.asarray(parameters, dtype=float)
    chosen = np.asarray(selected)
    if chosen.shape != track.times.shape or chosen.dtype != np.bool_ or not chosen.any():
        raise ValueError("selected must be a nonempty boolean row mask")
    expected = 5 if temporal else 3
    if theta.shape != (expected,) or not np.all(np.isfinite(theta)):
        raise ValueError(f"parameters must be a finite vector of length {expected}")
    observed = np.asarray(track.log_rx1_over_rx0, dtype=float)
    nuisance = (
        np.zeros_like(observed)
        if track.nuisance_mean is None
        else np.asarray(track.nuisance_mean, dtype=float)
    )
    if not temporal:
        mean = nuisance[None, :] + theta[0] + theta[1] * track.features.contrast
        density = _normal_log_density(observed[None, :] - mean, float(theta[2]))
        return density[:, chosen].sum(axis=1)

    mean = (
        nuisance[None, :]
        + theta[0]
        + theta[1] * track.features.contrast
        + theta[2] * track.features.change
    )
    residual = observed[None, :] - mean
    if not -4.0 <= float(theta[3]) <= 10.0:
        raise ValueError("log correlation time is outside the frozen numerical bounds")
    tau = math.exp(float(theta[3]))
    log_sigma = float(theta[4])

    def sequence_score(sequence_mask: np.ndarray) -> np.ndarray:
        output = np.zeros(len(track.log_weights))
        starts = sequence_mask & ~np.r_[False, sequence_mask[:-1]]
        pairs = sequence_mask[1:] & sequence_mask[:-1]
        # Stationary marginal for each disjoint sequence start, conditional
        # continuous-time innovations thereafter. No transition crosses a
        # partition boundary, and unequal observation gaps get unequal decay.
        output += _normal_log_density(residual[:, starts], log_sigma).sum(axis=1)
        rho = np.exp(-np.diff(track.times) / tau)
        if np.any(1.0 - rho * rho < 1e-8):
            raise ValueError("correlation is too close to its numerical boundary")
        innovations = residual[:, 1:] - rho[None, :] * residual[:, :-1]
        innovation_log_sigma = log_sigma + 0.5 * np.log1p(-(rho * rho))
        density = (
            -0.5 * math.log(2.0 * math.pi)
            - innovation_log_sigma[None, :]
            - 0.5 * (innovations / np.exp(innovation_log_sigma)[None, :]) ** 2
        )
        output += density[:, pairs].sum(axis=1)
        return output

    return sequence_score(chosen)


def projected_temporal_rank(track: ConditionalTrack, selected: object) -> int:
    """Minimum incremental derivative rank beyond static geometry and nuisances.

    A zero means the derivative is redundant with intercept, linear time, and
    the existing rowwise contrast for at least one candidate. Such a track must
    not contribute evidence for the temporal geometry extension.
    """
    validate_track(track)
    mask = np.asarray(selected)
    if mask.shape != track.times.shape or mask.dtype != np.bool_ or mask.sum() < 4:
        raise ValueError("rank mask must select at least four rows")
    time = track.times[mask]
    ranks = []
    for contrast, change in zip(
        track.features.contrast[:, mask], track.features.change[:, mask], strict=True
    ):
        nuisance = np.column_stack([np.ones(len(time)), time - time.mean(), contrast])
        projector = np.eye(len(time)) - nuisance @ np.linalg.pinv(nuisance)
        ranks.append(int(np.linalg.matrix_rank((projector @ change)[:, None], tol=1e-10)))
    return min(ranks)


def held_predictive_log_density(
    log_weights: object, training_scores: object, held_scores: object
) -> float:
    """Score held evidence with candidate weights fixed by training only."""
    weights = np.asarray(log_weights, dtype=float)
    training = np.asarray(training_scores, dtype=float)
    held = np.asarray(held_scores, dtype=float)
    if weights.ndim != 1 or training.shape != weights.shape or held.shape != weights.shape:
        raise ValueError("candidate score vectors must have identical nonempty shapes")
    if not np.all(np.isfinite(np.r_[weights, training, held])):
        raise ValueError("candidate scores must be finite")
    return _logsumexp(weights + training + held) - _logsumexp(weights + training)


def receiver_swap(track: ConditionalTrack) -> ConditionalTrack:
    """Swap provisional receiver geometry while retaining measured outcomes."""
    changed = CrossingFeatures(
        -track.features.contrast.copy(),
        -track.features.change.copy(),
        track.features.crossing_time.copy(),
        -track.features.crossing_coordinate.copy(),
    )
    return ConditionalTrack(
        track.track_id,
        track.log_weights.copy(),
        track.times.copy(),
        track.log_rx1_over_rx0.copy(),
        track.training_mask.copy(),
        changed,
        None if track.nuisance_mean is None else track.nuisance_mean.copy(),
    )


def deterministic_time_shuffle(track: ConditionalTrack, seed: int) -> ConditionalTrack:
    """Permute paired outcomes within each partition, preserving its membership."""
    validate_track(track)
    token = f"{seed}:{track.track_id}".encode()
    local_seed = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    generator = np.random.default_rng(local_seed)
    nuisance = (
        np.zeros_like(track.log_rx1_over_rx0)
        if track.nuisance_mean is None
        else track.nuisance_mean
    )
    residual = track.log_rx1_over_rx0 - nuisance
    changed_residual = residual.copy()
    for selected in (track.training_mask, ~track.training_mask):
        indices = np.flatnonzero(selected)
        changed_residual[indices] = residual[generator.permutation(indices)]
    changed = changed_residual + nuisance
    return ConditionalTrack(
        track.track_id,
        track.log_weights.copy(),
        track.times.copy(),
        changed,
        track.training_mask.copy(),
        track.features,
        None if track.nuisance_mean is None else track.nuisance_mean.copy(),
    )


def reverse_candidate_trajectory(track: ConditionalTrack) -> ConditionalTrack:
    """Reverse candidate trajectories without changing observed time order."""
    contrast = track.features.contrast[:, ::-1].copy()
    change = np.gradient(contrast, track.times, axis=1)
    crossing_time = np.array([_one_crossing_time(track.times, row) for row in contrast])
    duration = float(track.times[-1] - track.times[0])
    features = CrossingFeatures(
        contrast,
        change,
        crossing_time,
        (track.times[None, :] - crossing_time[:, None]) / duration,
    )
    return ConditionalTrack(
        track.track_id,
        track.log_weights.copy(),
        track.times.copy(),
        track.log_rx1_over_rx0.copy(),
        track.training_mask.copy(),
        features,
        None if track.nuisance_mean is None else track.nuisance_mean.copy(),
    )
