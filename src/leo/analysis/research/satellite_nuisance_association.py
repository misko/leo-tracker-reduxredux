"""Pure retrospective CFO/TLE association fits with bounded receiver nuisance.

This module owns no catalogue, filesystem, CLI, or plotting access.  Callers
provide one fixed candidate prediction matrix and one frozen measurement track;
the functions profile only the nuisance terms declared by the experiment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
IntArray = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class MeasurementTrack:
    """One aligned set of path measurements and split-safe responses."""

    time_s: FloatArray
    fit_cfo_hz: FloatArray
    response_cfo_hz: FloatArray
    path_index: IntArray
    radio_index: IntArray
    path_ids: tuple[str, ...]
    radio_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        size = self.time_s.size
        arrays = (
            self.fit_cfo_hz,
            self.response_cfo_hz,
            self.path_index,
            self.radio_index,
        )
        if size < 6 or any(item.shape != (size,) for item in arrays):
            raise ValueError("measurement track arrays must be aligned and nontrivial")
        if not np.all(np.isfinite(self.time_s)) or not np.all(np.isfinite(self.fit_cfo_hz)):
            raise ValueError("measurement fit inputs must be finite")
        if len(self.path_ids) < 1 or len(self.radio_ids) < 1:
            raise ValueError("measurement track requires path and radio identities")
        if np.any(self.path_index < 0) or np.any(self.path_index >= len(self.path_ids)):
            raise ValueError("path index falls outside the path inventory")
        if np.any(self.radio_index < 0) or np.any(self.radio_index >= len(self.radio_ids)):
            raise ValueError("radio index falls outside the radio inventory")
        for path in range(len(self.path_ids)):
            radios = np.unique(self.radio_index[self.path_index == path])
            if radios.size != 1:
                raise ValueError("every path must map to exactly one physical radio")


@dataclass(frozen=True, slots=True)
class CandidateFitBank:
    """Training-profiled nuisance and chronological response metrics."""

    penalized_training_rms_hz: FloatArray
    training_rms_hz: FloatArray
    evaluation_rms_hz: FloatArray
    full_response_rms_hz: FloatArray
    path_offsets_hz: FloatArray
    radio_rate_departures_hz_s: FloatArray


@dataclass(frozen=True, slots=True)
class NullFit:
    """One radio-only polynomial fitted without a satellite candidate."""

    degree: int
    coefficients_hz: tuple[float, ...]
    path_offsets_hz: tuple[float, ...]
    training_rms_hz: float
    evaluation_rms_hz: float


def chronological_mask(time_s: FloatArray, stop_fraction: float) -> BoolArray:
    """Select every row no later than a frozen fraction of the time span."""

    if not 0.0 < stop_fraction < 1.0:
        raise ValueError("chronological fraction must lie strictly inside zero and one")
    values = np.asarray(time_s, dtype=np.float64)
    start = float(np.min(values))
    stop = float(np.max(values))
    threshold = start + stop_fraction * (stop - start)
    return np.asarray(values <= threshold, dtype=np.bool_)


def chronological_block_mask(
    time_s: FloatArray,
    start_fraction: float,
    stop_fraction: float,
) -> BoolArray:
    """Select one half-open chronological fraction block."""

    if not 0.0 <= start_fraction < stop_fraction <= 1.0:
        raise ValueError("chronological block fractions are invalid")
    values = np.asarray(time_s, dtype=np.float64)
    start = float(np.min(values))
    stop = float(np.max(values))
    width = stop - start
    lower = start + start_fraction * width
    upper = start + stop_fraction * width
    if stop_fraction == 1.0:
        return np.asarray((values >= lower) & (values <= upper), dtype=np.bool_)
    return np.asarray((values >= lower) & (values < upper), dtype=np.bool_)


def fit_offset_candidates(
    track: MeasurementTrack,
    prediction_hz: FloatArray,
    training_mask: BoolArray,
    evaluation_mask: BoolArray,
) -> CandidateFitBank:
    """Profile one training-only CFO constant per path for every candidate."""

    predictions = _validate_fit_inputs(track, prediction_hz, training_mask, evaluation_mask)
    candidate_count = predictions.shape[0]
    offsets = np.zeros((candidate_count, len(track.path_ids)), dtype=np.float64)
    for path in range(len(track.path_ids)):
        selected = training_mask & (track.path_index == path)
        _require_support(selected, f"training path {path}")
        offsets[:, path] = np.mean(
            track.fit_cfo_hz[None, selected] - predictions[:, selected], axis=1
        )
    residual = track.response_cfo_hz[None, :] - predictions - offsets[:, track.path_index]
    training_residual = track.fit_cfo_hz[None, :] - predictions - offsets[:, track.path_index]
    zero_rates = np.zeros((candidate_count, len(track.radio_ids)), dtype=np.float64)
    training_rms = _equal_path_rms(training_residual, track.path_index, training_mask)
    return CandidateFitBank(
        penalized_training_rms_hz=training_rms.copy(),
        training_rms_hz=training_rms,
        evaluation_rms_hz=_equal_path_rms(residual, track.path_index, evaluation_mask),
        full_response_rms_hz=_equal_path_rms(
            residual,
            track.path_index,
            np.isfinite(track.response_cfo_hz),
        ),
        path_offsets_hz=offsets,
        radio_rate_departures_hz_s=zero_rates,
    )


def fit_hierarchical_candidates(
    track: MeasurementTrack,
    prediction_hz: FloatArray,
    training_mask: BoolArray,
    evaluation_mask: BoolArray,
    *,
    measurement_scale_hz: float,
    rate_prior_sigma_hz_s: float,
    maximum_rate_hz_s: float,
) -> CandidateFitBank:
    """Fit path offsets plus shrinkage-regularized physical-radio rates.

    Path offsets are analytically removed before estimating each radio rate.
    Rows receive inverse path-count weights, so every path contributes equally.
    The Gaussian prior is applied with the frozen measurement scale and the
    resulting rates are clipped to the declared hard nuisance boundary.
    """

    predictions = _validate_fit_inputs(track, prediction_hz, training_mask, evaluation_mask)
    for name, value in (
        ("measurement scale", measurement_scale_hz),
        ("rate prior sigma", rate_prior_sigma_hz_s),
        ("maximum rate", maximum_rate_hz_s),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive")
    candidate_count = predictions.shape[0]
    path_count = len(track.path_ids)
    radio_count = len(track.radio_ids)
    reference_s = float(np.mean(track.time_s[training_mask]))
    centered_time = track.time_s - reference_s
    raw = track.fit_cfo_hz[None, :] - predictions
    path_means = np.zeros((candidate_count, path_count), dtype=np.float64)
    path_time_means = np.zeros(path_count, dtype=np.float64)
    centered_raw = raw.copy()
    centered_path_time = centered_time.copy()
    for path in range(path_count):
        selected = training_mask & (track.path_index == path)
        _require_support(selected, f"training path {path}")
        path_means[:, path] = np.mean(raw[:, selected], axis=1)
        path_time_means[path] = float(np.mean(centered_time[selected]))
        centered_raw[:, selected] -= path_means[:, path, None]
        centered_path_time[selected] -= path_time_means[path]

    rates = np.zeros((candidate_count, radio_count), dtype=np.float64)
    prior_precision = measurement_scale_hz**2 / rate_prior_sigma_hz_s**2 / radio_count
    for radio in range(radio_count):
        numerator = np.zeros(candidate_count, dtype=np.float64)
        denominator = np.full(candidate_count, prior_precision, dtype=np.float64)
        radio_paths = [
            path
            for path in range(path_count)
            if np.any((track.path_index == path) & (track.radio_index == radio))
        ]
        if not radio_paths:
            raise ValueError(f"radio {radio} has no path support")
        for path in radio_paths:
            selected = training_mask & (track.path_index == path)
            x = centered_path_time[selected]
            numerator += np.mean(centered_raw[:, selected] * x[None, :], axis=1) / path_count
            denominator += np.mean(x**2) / path_count
        rates[:, radio] = np.clip(
            numerator / denominator,
            -maximum_rate_hz_s,
            maximum_rate_hz_s,
        )

    offsets = np.zeros((candidate_count, path_count), dtype=np.float64)
    for path in range(path_count):
        selected = training_mask & (track.path_index == path)
        radio = int(track.radio_index[selected][0])
        offsets[:, path] = np.mean(
            raw[:, selected] - rates[:, radio, None] * centered_time[selected][None, :],
            axis=1,
        )
    fitted_nuisance = (
        offsets[:, track.path_index] + rates[:, track.radio_index] * centered_time[None, :]
    )
    training_residual = track.fit_cfo_hz[None, :] - predictions - fitted_nuisance
    response_residual = track.response_cfo_hz[None, :] - predictions - fitted_nuisance
    training_mse = _equal_path_mse(training_residual, track.path_index, training_mask)
    penalty = measurement_scale_hz**2 * np.mean(np.square(rates / rate_prior_sigma_hz_s), axis=1)
    return CandidateFitBank(
        penalized_training_rms_hz=np.sqrt(training_mse + penalty),
        training_rms_hz=np.sqrt(training_mse),
        evaluation_rms_hz=_equal_path_rms(response_residual, track.path_index, evaluation_mask),
        full_response_rms_hz=_equal_path_rms(
            response_residual,
            track.path_index,
            np.isfinite(track.response_cfo_hz),
        ),
        path_offsets_hz=offsets,
        radio_rate_departures_hz_s=rates,
    )


def fit_radio_polynomial_null(
    track: MeasurementTrack,
    training_mask: BoolArray,
    evaluation_mask: BoolArray,
    *,
    degree: int,
) -> NullFit:
    """Fit path constants plus one shared linear or quadratic radio curve."""

    if degree not in (1, 2):
        raise ValueError("radio-only null degree must be one or two")
    _validate_masks(track, training_mask, evaluation_mask)
    reference_s = float(np.mean(track.time_s[training_mask]))
    centered = track.time_s - reference_s
    columns = [
        np.asarray(track.path_index == path, dtype=np.float64)
        for path in range(len(track.path_ids))
    ]
    columns.extend(centered**order for order in range(1, degree + 1))
    design = np.column_stack(columns)
    weights = np.zeros(track.time_s.size, dtype=np.float64)
    for path in range(len(track.path_ids)):
        selected = training_mask & (track.path_index == path)
        _require_support(selected, f"training path {path}")
        weights[selected] = 1.0 / math.sqrt(int(np.count_nonzero(selected)))
    weighted_design = design[training_mask] * weights[training_mask, None]
    weighted_response = track.fit_cfo_hz[training_mask] * weights[training_mask]
    coefficients, *_ = np.linalg.lstsq(weighted_design, weighted_response, rcond=None)
    predicted = design @ coefficients
    training_residual = track.fit_cfo_hz - predicted
    response_residual = track.response_cfo_hz - predicted
    return NullFit(
        degree=degree,
        coefficients_hz=tuple(float(value) for value in coefficients[len(track.path_ids) :]),
        path_offsets_hz=tuple(float(value) for value in coefficients[: len(track.path_ids)]),
        training_rms_hz=float(
            _equal_path_rms(training_residual[None, :], track.path_index, training_mask)[0]
        ),
        evaluation_rms_hz=float(
            _equal_path_rms(response_residual[None, :], track.path_index, evaluation_mask)[0]
        ),
    )


def permute_fit_response_within_paths(
    track: MeasurementTrack,
    training_mask: BoolArray,
    rng: np.random.Generator,
) -> MeasurementTrack:
    """Return a deterministic control with training CFO order permuted per path."""

    permuted = track.fit_cfo_hz.copy()
    for path in range(len(track.path_ids)):
        indexes = np.flatnonzero(training_mask & (track.path_index == path))
        if indexes.size:
            permuted[indexes] = permuted[rng.permutation(indexes)]
    return MeasurementTrack(
        time_s=track.time_s,
        fit_cfo_hz=permuted,
        response_cfo_hz=track.response_cfo_hz,
        path_index=track.path_index,
        radio_index=track.radio_index,
        path_ids=track.path_ids,
        radio_ids=track.radio_ids,
    )


def _validate_fit_inputs(
    track: MeasurementTrack,
    prediction_hz: FloatArray,
    training_mask: BoolArray,
    evaluation_mask: BoolArray,
) -> FloatArray:
    predictions = np.asarray(prediction_hz, dtype=np.float64)
    if predictions.ndim != 2 or predictions.shape[1] != track.time_s.size:
        raise ValueError("candidate prediction matrix must be candidate by measurement")
    if predictions.shape[0] < 1 or not np.all(np.isfinite(predictions)):
        raise ValueError("candidate prediction matrix must be finite and nonempty")
    _validate_masks(track, training_mask, evaluation_mask)
    return predictions


def _validate_masks(
    track: MeasurementTrack,
    training_mask: BoolArray,
    evaluation_mask: BoolArray,
) -> None:
    if training_mask.shape != track.time_s.shape or evaluation_mask.shape != track.time_s.shape:
        raise ValueError("fit masks must align with measurements")
    if np.any(training_mask & evaluation_mask):
        raise ValueError("training and evaluation masks must be disjoint")
    _require_support(training_mask, "training")
    _require_support(evaluation_mask & np.isfinite(track.response_cfo_hz), "evaluation")


def _require_support(mask: BoolArray, label: str) -> None:
    if int(np.count_nonzero(mask)) < 2:
        raise ValueError(f"{label} requires at least two rows")


def _equal_path_mse(
    residual_hz: FloatArray,
    path_index: IntArray,
    mask: BoolArray,
) -> FloatArray:
    values = []
    for path in sorted(set(int(value) for value in path_index[mask])):
        selected = mask & (path_index == path) & np.isfinite(residual_hz[0])
        if np.any(selected):
            values.append(np.mean(np.square(residual_hz[:, selected]), axis=1))
    if not values:
        raise ValueError("equal-path metric has no finite path support")
    return np.mean(np.stack(values, axis=0), axis=0)


def _equal_path_rms(
    residual_hz: FloatArray,
    path_index: IntArray,
    mask: BoolArray,
) -> FloatArray:
    return np.sqrt(_equal_path_mse(residual_hz, path_index, mask))
