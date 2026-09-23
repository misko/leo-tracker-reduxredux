"""Random-group candidate phase validation for one source-bound pilot locklet.

This research scorer consumes measured modulo-pi phase advances and frozen
candidate phase integrals.  It profiles one locklet-local frequency bias using
training groups only, then evaluates circular residuals on held groups.  It is
not a production association contract and does not establish satellite identity.
"""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class CandidatePhaseEvidence:
    measured_phase_advance_rad: np.ndarray
    interval_duration_s: np.ndarray
    group_id: np.ndarray
    training_group_ids: tuple[Hashable, ...]
    candidate_integrated_phase_rad: np.ndarray
    candidate_ids: tuple[str, ...]
    split_seed: int
    endpoint_frame_ids: np.ndarray


@dataclass(frozen=True, slots=True)
class CandidatePhaseValidation:
    candidate_ids: tuple[str, ...]
    fitted_bias_hz: np.ndarray
    training_composite_score: np.ndarray
    heldout_composite_score: np.ndarray
    heldout_residual_rad: np.ndarray
    training_group_ids: tuple[Hashable, ...]
    heldout_group_ids: tuple[Hashable, ...]
    candidate_contrast_rms_rad: np.ndarray
    maximum_candidate_contrast_rad: float
    identifiable_after_nuisance: bool
    split_seed: int


def seeded_group_split(
    group_ids: tuple[Hashable, ...], *, seed: int, heldout_fraction: float = 0.5
) -> tuple[tuple[Hashable, ...], tuple[Hashable, ...]]:
    """Randomly assign whole groups, retaining at least two on each side."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("phase split seed must be an integer")
    if not 0 < heldout_fraction < 1:
        raise ValueError("heldout fraction must lie in (0, 1)")
    unique = tuple(dict.fromkeys(group_ids))
    if len(unique) < 4:
        raise ValueError("candidate phase validation needs at least four groups")
    order = np.random.default_rng(seed).permutation(len(unique))
    held_count = min(len(unique) - 2, max(2, round(len(unique) * heldout_fraction)))
    held_indexes = frozenset(int(value) for value in order[:held_count])
    training = tuple(value for index, value in enumerate(unique) if index not in held_indexes)
    heldout = tuple(value for index, value in enumerate(unique) if index in held_indexes)
    return training, heldout


def score_candidate_integrated_phase(
    evidence: CandidatePhaseEvidence,
    *,
    bias_period_hz: float = 375.0,
    bias_grid_points: int = 3001,
    concentration: float = 4.0,
    minimum_identifiable_contrast_rad: float = 0.10,
) -> CandidatePhaseValidation:
    """Profile candidate-local bias on train and score random held groups.

    Scores are equal-group conditional composite scores, not calibrated
    posterior probabilities.  Candidate phase and all policy values must be
    frozen before held-out evaluation.
    """
    measured, duration, groups, prediction = _validated_arrays(evidence)
    if (
        not math.isfinite(bias_period_hz)
        or bias_period_hz <= 0
        or isinstance(bias_grid_points, bool)
        or not isinstance(bias_grid_points, int)
        or bias_grid_points < 101
        or bias_grid_points % 2 == 0
        or not math.isfinite(concentration)
        or concentration <= 0
        or not math.isfinite(minimum_identifiable_contrast_rad)
        or minimum_identifiable_contrast_rad < 0
    ):
        raise ValueError("candidate phase scoring policy is invalid")
    training_ids = tuple(evidence.training_group_ids)
    training_set = set(training_ids)
    observed_ids = set(groups.tolist())
    if len(training_ids) < 2 or len(training_set) != len(training_ids):
        raise ValueError("training group ids must contain at least two unique groups")
    if not training_set < observed_ids:
        raise ValueError("training groups must be a strict subset of observed groups")
    heldout_ids = tuple(
        value for value in dict.fromkeys(groups.tolist()) if value not in training_set
    )
    if len(heldout_ids) < 2:
        raise ValueError("candidate phase validation needs at least two held-out groups")
    training = np.asarray([value in training_set for value in groups], dtype=bool)
    _reject_endpoint_leakage(evidence.endpoint_frame_ids, groups, training, len(measured))

    bias_grid = np.linspace(
        -bias_period_hz / 2,
        bias_period_hz / 2,
        num=bias_grid_points,
        endpoint=False,
    )
    bias_phase = 2 * np.pi * bias_grid[:, None] * duration[None, :]
    fitted_bias = np.empty(len(prediction), dtype=float)
    training_score = np.empty(len(prediction), dtype=float)
    heldout_score = np.empty(len(prediction), dtype=float)
    heldout_residual = np.full(prediction.shape, np.nan, dtype=float)
    fitted_prediction = np.empty(prediction.shape, dtype=float)
    for index, candidate in enumerate(prediction):
        residual_grid = _wrap_pi(measured[None, :] - candidate[None, :] - bias_phase)
        grid_scores = np.asarray(
            [
                _equal_group_score(residual, groups, training_ids, concentration)
                for residual in residual_grid
            ]
        )
        choice = int(np.argmax(grid_scores))
        fitted_bias[index] = bias_grid[choice]
        training_score[index] = grid_scores[choice]
        residual = _wrap_pi(measured - candidate - bias_phase[choice])
        heldout_residual[index, ~training] = residual[~training]
        heldout_score[index] = _equal_group_score(residual, groups, heldout_ids, concentration)
        fitted_prediction[index] = candidate + bias_phase[choice]

    contrast = np.zeros((len(prediction), len(prediction)), dtype=float)
    for left in range(len(prediction)):
        for right in range(left + 1, len(prediction)):
            difference = _wrap_pi(
                fitted_prediction[left, ~training] - fitted_prediction[right, ~training]
            )
            value = _equal_group_rms(difference, groups[~training], heldout_ids)
            contrast[left, right] = contrast[right, left] = value
    maximum_contrast = float(np.max(contrast))
    return CandidatePhaseValidation(
        candidate_ids=evidence.candidate_ids,
        fitted_bias_hz=fitted_bias,
        training_composite_score=training_score,
        heldout_composite_score=heldout_score,
        heldout_residual_rad=heldout_residual,
        training_group_ids=training_ids,
        heldout_group_ids=heldout_ids,
        candidate_contrast_rms_rad=contrast,
        maximum_candidate_contrast_rad=maximum_contrast,
        identifiable_after_nuisance=maximum_contrast >= minimum_identifiable_contrast_rad,
        split_seed=evidence.split_seed,
    )


def _validated_arrays(evidence):
    measured = np.asarray(evidence.measured_phase_advance_rad, dtype=float)
    duration = np.asarray(evidence.interval_duration_s, dtype=float)
    groups = np.asarray(evidence.group_id)
    prediction = np.asarray(evidence.candidate_integrated_phase_rad, dtype=float)
    if (
        measured.ndim != 1
        or len(measured) < 4
        or duration.shape != measured.shape
        or groups.shape != measured.shape
        or prediction.ndim != 2
        or prediction.shape[1] != len(measured)
        or prediction.shape[0] != len(evidence.candidate_ids)
        or len(set(evidence.candidate_ids)) != len(evidence.candidate_ids)
        or not evidence.candidate_ids
    ):
        raise ValueError("candidate phase arrays or identities have incompatible shapes")
    if (
        not np.all(np.isfinite(measured))
        or not np.all(np.isfinite(duration))
        or not np.all(duration > 0)
        or not np.all(np.isfinite(prediction))
        or isinstance(evidence.split_seed, bool)
        or not isinstance(evidence.split_seed, int)
    ):
        raise ValueError("candidate phase values and split seed must be finite and valid")
    return measured, duration, groups, prediction


def _reject_endpoint_leakage(endpoints, groups, training, count):
    values = np.asarray(endpoints)
    if values.shape != (count, 2):
        raise ValueError("endpoint frame ids must be interval by two endpoints")
    group_by_frame = {}
    for group, frame_ids in zip(groups.tolist(), values.tolist(), strict=True):
        for frame_id in frame_ids:
            previous = group_by_frame.setdefault(frame_id, group)
            if previous != group:
                raise ValueError("a frame endpoint appears in different phase groups")
    train_frames = set(values[training].reshape(-1).tolist())
    held_frames = set(values[~training].reshape(-1).tolist())
    if train_frames & held_frames:
        raise ValueError("a frame endpoint crosses the training boundary")


def _wrap_pi(value):
    return (np.asarray(value) + np.pi / 2) % np.pi - np.pi / 2


def _equal_group_score(residual, groups, selected_ids, concentration):
    group_scores = []
    for group_id in selected_ids:
        selected = groups == group_id
        if not np.any(selected):
            raise ValueError("declared phase group has no intervals")
        group_scores.append(float(np.mean(concentration * np.cos(2 * residual[selected]))))
    return float(np.mean(group_scores))


def _equal_group_rms(values, groups, selected_ids):
    return math.sqrt(
        math.fsum(float(np.mean(np.square(values[groups == item]))) for item in selected_ids)
        / len(selected_ids)
    )
