"""Pure, held-out broadband alignment of two simultaneous complex receivers."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class BroadbandAlignmentModel:
    reference_sample: float
    frequency_reference_hz: float
    relative_cfo_hz: float
    relative_cfo_rate_hz_s: float
    fractional_delay_samples: float
    phase_rad: float
    frequency_hz: tuple[float, ...]
    channel_transfer: tuple[complex, ...]
    relative_cfo_standard_error_hz: float
    relative_cfo_rate_standard_error_hz_s: float
    fractional_delay_standard_error_samples: float
    phase_standard_error_rad: float
    uncertainty_kind: str


@dataclass(frozen=True, slots=True)
class AlignmentValidation:
    raw_coherence: float
    corrected_coherence: float
    wrong_time_coherence: float
    coherent_bin_count: int
    covered_bandwidth_hz: float
    corrected_cross_phase_rad: float
    corrected_cross_real: float
    normalized_complex_error: float


@dataclass(frozen=True, slots=True)
class BroadbandAlignmentResult:
    model: BroadbandAlignmentModel
    training: AlignmentValidation
    held_out: AlignmentValidation
    training_frequency_hz: tuple[float, ...]
    training_bin_coherence: tuple[float, ...]
    training_cross_phase_rad: tuple[float, ...]
    training_physical_overlap_mask: tuple[bool, ...]
    training_block_time_s: tuple[float, ...]
    training_block_phase_rad: tuple[float, ...]


def _coherence(left: np.ndarray, right: np.ndarray) -> float:
    cross = abs(np.vdot(left, right))
    return float(
        cross / math.sqrt(max(float(np.vdot(left, left).real * np.vdot(right, right).real), 1e-30))
    )


def _robust_polynomial(time_s: np.ndarray, phase: np.ndarray, weight: np.ndarray) -> np.ndarray:
    design = np.column_stack((np.ones(len(time_s)), time_s, 0.5 * time_s**2))
    fit_weight = np.asarray(weight, float).copy()
    coefficients = np.zeros(3)
    for _ in range(6):
        root = np.sqrt(fit_weight)
        coefficients = np.linalg.lstsq(design * root[:, None], phase * root, rcond=None)[0]
        residual = phase - design @ coefficients
        scale = 1.4826 * np.median(abs(residual - np.median(residual))) + 1e-12
        fit_weight = weight * np.minimum(1.0, 1.5 * scale / np.maximum(abs(residual), 1e-30))
    return coefficients


def _group_phase_fit(time_s, phasors, groups, degree):
    """Fit local frequency/rate with independent intercepts across group gaps.

    Only unwrap inside a supplied group. Independent group intercepts prevent
    an assumed integer-cycle connection across missing or held-out intervals.
    """
    labels = np.unique(groups)
    phase = np.empty(len(time_s))
    for group in labels:
        selected = groups == group
        if np.sum(selected) < 3:
            raise ValueError("each phase-fit group needs at least three blocks")
        # A conservative ambiguity screen, not proof that no cycle slips exist.
        increments = np.angle(phasors[selected][1:] * phasors[selected][:-1].conj())
        if np.any(abs(increments) >= 0.9 * np.pi):
            raise ValueError("ambiguous local phase increment near pi")
        phase[selected] = np.unwrap(np.angle(phasors[selected]))
    columns = [groups == group for group in labels] + [time_s]
    if degree == 2:
        columns.append(0.5 * time_s**2)
    design = np.column_stack(columns).astype(float)
    if np.linalg.matrix_rank(design) < design.shape[1]:
        raise ValueError("grouped carrier fit is underdetermined")
    weight = abs(phasors)
    fitted_weight = weight.copy()
    for _ in range(6):
        root = np.sqrt(fitted_weight)
        fitted = np.linalg.lstsq(design * root[:, None], phase * root, rcond=None)[0]
        residual = phase - design @ fitted
        scale = 1.4826 * np.median(abs(residual - np.median(residual))) + 1e-12
        fitted_weight = weight * np.minimum(1, 1.5 * scale / np.maximum(abs(residual), 1e-30))
    coefficients = np.array(
        [
            float(np.angle(np.mean(np.exp(1j * fitted[: len(labels)])))),
            fitted[len(labels)],
            fitted[-1] if degree == 2 else 0.0,
        ]
    )
    covariance = np.linalg.pinv(design.T @ design) * float(
        np.sum(residual**2) / max(len(time_s) - design.shape[1], 1)
    )
    frequency_variance = float(covariance[len(labels), len(labels)])
    rate_variance = float(covariance[-1, -1]) if degree == 2 else 0.0
    return coefficients, phase, residual, frequency_variance, rate_variance


def _derotate(values: np.ndarray, rate: float, model: BroadbandAlignmentModel) -> np.ndarray:
    sample = np.arange(len(values), dtype=float)
    delta_s = (sample - model.reference_sample) / rate
    phase = (
        2
        * np.pi
        * (model.relative_cfo_hz * delta_s + 0.5 * model.relative_cfo_rate_hz_s * delta_s**2)
    )
    return values[:, 1] * np.exp(-1j * phase)


def apply_broadband_alignment(
    iq: npt.NDArray[np.complexfloating], sample_rate_hz: float, model: BroadbandAlignmentModel
) -> npt.NDArray[np.complex128]:
    """Apply the temporal CFO/rate model to RX1.

    The sparse frequency response is intentionally not inverted here: gaps in
    qualified physical support must not be interpolated as measured bandwidth.
    Use ``model.frequency_hz`` and ``model.channel_transfer`` for blockwise
    forward prediction on exactly those recorded bins.
    """
    values = np.asarray(iq)
    corrected = np.asarray(values, np.complex128).copy()
    corrected[:, 1] = _derotate(values, sample_rate_hz, model)
    return corrected


def estimate_broadband_alignment(
    iq: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    *,
    receiver_cfo_seed_hz: float | None = None,
    cfo_search_half_width_hz: float = 900_000.0,
    training_fraction: float = 0.5,
    block_samples: int = 4096,
    frequency_mask: npt.NDArray[np.bool_] | None = None,
    channel_smoothing_bins: int = 0,
    spectral_guard_hz: float = 0.0,
    maximum_delay_samples: int = 8,
    training_block_indices: tuple[int, ...] | None = None,
    training_group_ids: tuple[int, ...] | None = None,
    heldout_block_indices: tuple[int, ...] | None = None,
    heldout_group_ids: tuple[int, ...] | None = None,
    random_seed: int = 3107,
) -> BroadbandAlignmentResult:
    """Fit a frozen channel on training data and validate on unused blocks.

    Explicit training blocks preserve physical timestamps across a random group
    split. Their group IDs also define randomized inner model-selection folds.
    The historical first/second partition remains available for legacy callers.

    Frequencies use RX0 coordinates. A bin is eligible only when both its RX0
    frequency and its physical RX1 partner ``f + relative_cfo`` lie inside the
    sampled Nyquist interval; FFT wrapping never creates common bandwidth.
    """
    values = np.asarray(iq)
    if values.ndim != 2 or values.shape[1] != 2 or not np.iscomplexobj(values):
        raise ValueError("IQ must contain two complex receiver columns")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0 or len(values) < 4 * block_samples:
        raise ValueError("sample rate and record length must support four blocks")
    split = int(len(values) * training_fraction)
    if not block_samples <= split <= len(values) - block_samples:
        raise ValueError("training fraction leaves insufficient train or held data")
    random_blocks = training_block_indices is not None
    training_mask = None
    selected_starts = None
    groups = None
    explicit_held_starts = None
    if random_blocks:
        indexes = np.asarray(training_block_indices)
        group_array = np.asarray(training_group_ids)
        count = len(values) // block_samples
        if (
            indexes.ndim != 1
            or len(indexes) < 6
            or indexes.dtype.kind not in "iu"
            or len(np.unique(indexes)) != len(indexes)
            or np.any(indexes < 0)
            or np.any(indexes >= count)
            or len(indexes) >= count
            or group_array.shape != indexes.shape
            or group_array.dtype.kind not in "iu"
            or len(np.unique(group_array)) < 3
        ):
            raise ValueError(
                "random training requires distinct valid blocks and at least three groups"
            )
        order = np.argsort(indexes)
        selected_starts = indexes[order] * block_samples
        groups = group_array[order]
        for group in np.unique(groups):
            if np.any(np.diff(indexes[order][groups == group]) != 1):
                raise ValueError("training blocks within each group must be consecutive")
        if heldout_block_indices is not None:
            held_indexes = np.asarray(heldout_block_indices)
            held_groups = np.asarray(heldout_group_ids)
            if (
                held_indexes.ndim != 1
                or held_indexes.dtype.kind not in "iu"
                or len(held_indexes) < 2
                or len(np.unique(held_indexes)) != len(held_indexes)
                or np.any(held_indexes < 0)
                or np.any(held_indexes >= count)
                or len(np.intersect1d(indexes, held_indexes))
                or held_groups.shape != held_indexes.shape
                or held_groups.dtype.kind not in "iu"
                or len(np.intersect1d(groups, held_groups))
            ):
                raise ValueError("held blocks must be distinct, valid and disjoint from training")
            explicit_held_starts = np.sort(held_indexes) * block_samples
        else:
            raise ValueError("random group fitting requires explicit held blocks and groups")
        training_mask = np.zeros(len(values), dtype=bool)
        for start in selected_starts:
            training_mask[start : start + block_samples] = True
        train = values
    else:
        if (
            training_group_ids is not None
            or heldout_block_indices is not None
            or heldout_group_ids is not None
        ):
            raise ValueError("training groups and held blocks require explicit training blocks")
        train = values[:split]
    size = 1 << math.ceil(math.log2(len(train)))
    frequencies = np.fft.fftshift(np.fft.fftfreq(size, 1 / sample_rate_hz))
    seed = 0.0 if receiver_cfo_seed_hz is None else float(receiver_cfo_seed_hz)
    bounded = abs(frequencies - seed) <= cfo_search_half_width_hz
    if not np.any(bounded):
        raise ValueError("CFO search does not contain a sampled frequency")
    best = None
    for lag in range(-maximum_delay_samples, maximum_delay_samples + 1):
        if lag >= 0:
            left, right = train[: len(train) - lag or None, 0], train[lag:, 1]
        else:
            left, right = train[-lag:, 0], train[: len(train) + lag, 1]
        candidate_product = right * np.conj(left)
        if training_mask is not None:
            if lag >= 0:
                valid = training_mask[: len(train) - lag or None] & training_mask[lag:]
            else:
                valid = training_mask[-lag:] & training_mask[: len(train) + lag]
            # Both receiver samples must belong to training, including lag edges.
            candidate_product = np.where(valid, candidate_product, 0.0)
        candidate_spectrum = np.fft.fftshift(
            np.fft.fft(candidate_product * np.hanning(len(candidate_product)), size)
        )
        score = float(np.max(abs(candidate_spectrum[bounded])))
        if best is None or score > best[0]:
            best = (score, lag, candidate_product, candidate_spectrum)
    assert best is not None
    _, integer_delay, product, spectrum = best
    coarse = float(frequencies[np.flatnonzero(bounded)[np.argmax(abs(spectrum[bounded]))]])

    starts = (
        np.arange(0, len(product) - block_samples + 1, block_samples)
        if selected_starts is None
        else selected_starts
    )
    if selected_starts is not None and starts[-1] + block_samples > len(product):
        raise ValueError("training block reaches beyond lag-valid samples")
    centers = starts + (block_samples - 1) / 2
    reference = float(np.average(centers))
    block_phasor = np.asarray(
        [
            np.sum(
                product[start : start + block_samples]
                * np.exp(
                    -2j * np.pi * coarse * np.arange(start, start + block_samples) / sample_rate_hz
                )
            )
            for start in starts
        ]
    )
    time_s = (centers - reference) / sample_rate_hz
    block_phase = np.unwrap(np.angle(block_phasor)) if groups is None else np.angle(block_phasor)
    coefficients = (
        _robust_polynomial(time_s, block_phase, abs(block_phasor))
        if groups is None
        else _group_phase_fit(time_s, block_phasor, groups, 2)[0]
    )
    if groups is not None:
        # Every selection fold consists of whole training groups, randomized
        # once. No outer held samples enter phase unwrapping or complexity choice.
        shuffled = np.random.default_rng(random_seed).permutation(np.unique(groups))
        cv: dict[int, list[np.float64]] = {1: [], 2: []}
        for withheld in np.array_split(shuffled, min(3, len(shuffled))):
            held = np.isin(groups, withheld)
            retained = ~held
            for degree in (1, 2):
                params = _group_phase_fit(
                    time_s[retained], block_phasor[retained], groups[retained], degree
                )[0]
                for group in withheld:
                    selected = groups == group
                    tt = time_s[selected]
                    zz = block_phasor[selected]
                    # Wrapped within-group increments need no held unwrap or
                    # fitted held phase offset. Never bridge distinct groups.
                    residual = np.angle(
                        zz[1:]
                        * zz[:-1].conj()
                        * np.exp(-1j * (params[1] * np.diff(tt) + 0.5 * params[2] * np.diff(tt**2)))
                    )
                    cv[degree].extend(residual)
        quadratic_selected = np.sqrt(np.mean(np.square(cv[2]))) < 0.8 * np.sqrt(
            np.mean(np.square(cv[1]))
        )
        coefficients, block_phase, grouped_residual, grouped_fvar, grouped_rvar = _group_phase_fit(
            time_s, block_phasor, groups, 2 if quadratic_selected else 1
        )
    if groups is None:
        internal = max(3, 2 * len(time_s) // 3)
        linear_design = np.column_stack((np.ones(internal), time_s[:internal]))
        root = np.sqrt(abs(block_phasor[:internal]))
        linear = np.linalg.lstsq(
            linear_design * root[:, None], block_phase[:internal] * root, rcond=None
        )[0]
        quadratic_training = _robust_polynomial(
            time_s[:internal], block_phase[:internal], abs(block_phasor[:internal])
        )
        held_time = time_s[internal:]
        quadratic_selected = True
        if len(held_time):
            linear_residual = np.angle(
                np.exp(1j * (block_phase[internal:] - linear[0] - linear[1] * held_time))
            )
            linear_error = np.sqrt(np.mean(linear_residual**2))
            quadratic_residual = np.angle(
                np.exp(
                    1j
                    * (
                        block_phase[internal:]
                        - quadratic_training[0]
                        - quadratic_training[1] * held_time
                        - 0.5 * quadratic_training[2] * held_time**2
                    )
                )
            )
            quadratic_error = np.sqrt(np.mean(quadratic_residual**2))
            if not quadratic_error < 0.8 * linear_error:
                quadratic_selected = False
                full_design = np.column_stack((np.ones(len(time_s)), time_s))
                full_root = np.sqrt(abs(block_phasor))
                selected = np.linalg.lstsq(
                    full_design * full_root[:, None], block_phase * full_root, rcond=None
                )[0]
                coefficients = np.asarray((selected[0], selected[1], 0.0))
    cfo = coarse + coefficients[1] / (2 * np.pi)
    rate_hz_s = coefficients[2] / (2 * np.pi)

    if groups is None:
        time_design = np.column_stack((np.ones(len(time_s)), time_s, 0.5 * time_s**2))
        time_residual = np.unwrap(np.angle(block_phasor)) - time_design @ coefficients
        time_covariance = np.linalg.pinv(time_design.T @ time_design) * float(
            np.sum(time_residual**2) / max(len(time_s) - 3, 1)
        )
        cfo_se = math.sqrt(max(float(time_covariance[1, 1]), 0.0)) / (2 * np.pi)
        rate_se = math.sqrt(max(float(time_covariance[2, 2]), 0.0)) / (2 * np.pi)
    else:
        cfo_se = math.sqrt(max(grouped_fvar, 0)) / (2 * np.pi)
        rate_se = math.sqrt(max(grouped_rvar, 0)) / (2 * np.pi)
    leave_chunk_parameters = []
    omissions = (
        np.array_split(np.arange(len(time_s)), min(4, len(time_s)))
        if groups is None
        else [np.flatnonzero(groups == group) for group in np.unique(groups)]
    )
    for omitted in omissions:
        retained = np.ones(len(time_s), dtype=bool)
        retained[omitted] = False
        if np.sum(retained) < 3:
            continue
        if groups is not None:
            refit = _group_phase_fit(
                time_s[retained],
                block_phasor[retained],
                groups[retained],
                2 if quadratic_selected else 1,
            )[0]
        elif quadratic_selected:
            refit = _robust_polynomial(
                time_s[retained], block_phase[retained], abs(block_phasor[retained])
            )
        else:
            design = np.column_stack((np.ones(int(np.sum(retained))), time_s[retained]))
            fit_root = np.sqrt(abs(block_phasor[retained]))
            fitted = np.linalg.lstsq(
                design * fit_root[:, None], block_phase[retained] * fit_root, rcond=None
            )[0]
            refit = np.asarray((fitted[0], fitted[1], 0.0))
        leave_chunk_parameters.append(refit)
    if len(leave_chunk_parameters) > 1:
        scatter = np.std(np.asarray(leave_chunk_parameters), axis=0, ddof=1)
        cfo_se = max(cfo_se, float(scatter[1]) / (2 * np.pi))
        rate_se = max(rate_se, float(scatter[2]) / (2 * np.pi))
    provisional = BroadbandAlignmentModel(
        reference,
        0.0,
        cfo,
        rate_hz_s,
        0.0,
        coefficients[0],
        (),
        (),
        cfo_se,
        rate_se,
        math.nan,
        math.nan,
        "conditional_weighted_fit_scatter_not_calibrated_ci",
    )
    rx1 = _derotate(values, sample_rate_hz, provisional)
    fft_frequency = np.fft.fftshift(np.fft.fftfreq(block_samples, 1 / sample_rate_hz))
    nyquist = sample_rate_hz / 2 - spectral_guard_hz
    record_times = (np.asarray((0.0, len(values) - 1.0)) - reference) / sample_rate_hz
    physical_overlap = abs(fft_frequency) <= nyquist
    for endpoint_cfo in cfo + rate_hz_s * record_times:
        physical_overlap &= abs(fft_frequency + endpoint_cfo) <= nyquist
    erosion_bins = 15
    physical_overlap &= np.convolve(
        physical_overlap.astype(int), np.ones(2 * erosion_bins + 1, dtype=int), mode="same"
    ) == (2 * erosion_bins + 1)
    eligible = physical_overlap.copy()
    if frequency_mask is not None:
        supplied = np.asarray(frequency_mask, bool)
        if supplied.shape != eligible.shape:
            raise ValueError("frequency mask must match block FFT bins")
        eligible &= supplied
    cross = np.zeros(block_samples, complex)
    power0 = np.zeros(block_samples)
    power1 = np.zeros(block_samples)
    window = np.hanning(block_samples)
    for start in starts:
        left = np.fft.fftshift(np.fft.fft(values[start : start + block_samples, 0] * window))
        right = np.fft.fftshift(np.fft.fft(rx1[start : start + block_samples] * window))
        cross += right * np.conj(left)
        power0 += abs(left) ** 2
        power1 += abs(right) ** 2
    smoothing = 31
    kernel = np.ones(smoothing) / smoothing
    smooth_cross = np.convolve(cross, kernel, mode="same")
    smooth_power0 = np.convolve(power0, kernel, mode="same")
    smooth_power1 = np.convolve(power1, kernel, mode="same")
    bin_coherence = abs(smooth_cross) / np.sqrt(np.maximum(smooth_power0 * smooth_power1, 1e-30))
    # A deterministic time-block permutation supplies a phase-blind empirical
    # null with the same spectra and smoothing as the candidate cross-spectrum.
    null_cross = np.zeros(block_samples, complex)
    spectra0, spectra1 = [], []
    for start in starts:
        spectra0.append(
            np.fft.fftshift(np.fft.fft(values[start : start + block_samples, 0] * window))
        )
        spectra1.append(np.fft.fftshift(np.fft.fft(rx1[start : start + block_samples] * window)))
    for left, right in zip(spectra0, np.roll(np.asarray(spectra1), 7, axis=0), strict=True):
        null_cross += right * np.conj(left)
    null_coherence = abs(np.convolve(null_cross, kernel, mode="same")) / np.sqrt(
        np.maximum(smooth_power0 * smooth_power1, 1e-30)
    )
    null_gate = max(0.05, 3 * float(np.median(null_coherence[physical_overlap])))
    eligible &= bin_coherence >= null_gate
    indexes = np.flatnonzero(eligible)
    if len(indexes) < 8:
        raise ValueError("fewer than eight coherent physical-overlap bins")
    phase = np.angle(smooth_cross[indexes])
    weight = np.minimum(abs(smooth_cross[indexes]), np.percentile(abs(smooth_cross[indexes]), 90))
    frequency_center = float(np.average(fft_frequency[indexes], weights=weight))
    centered_frequency = fft_frequency[indexes] - frequency_center
    delay_grid = np.linspace(-maximum_delay_samples, maximum_delay_samples, 1601)
    delay_score = np.asarray(
        [
            abs(
                np.sum(
                    weight
                    * np.exp(1j * phase)
                    * np.exp(2j * np.pi * centered_frequency * delay / sample_rate_hz)
                )
            )
            for delay in delay_grid
        ]
    )
    delay = float(delay_grid[int(np.argmax(delay_score))])
    corrected_spectral = np.exp(1j * phase) * np.exp(
        2j * np.pi * centered_frequency * delay / sample_rate_hz
    )
    intercept = float(np.angle(np.sum(weight * corrected_spectral)))
    spectral_residual = np.angle(corrected_spectral * np.exp(-1j * intercept))
    residual_variance = float(np.average(spectral_residual**2, weights=weight))
    frequency_information = float(np.sum(weight * centered_frequency**2) / np.sum(weight))
    effective_bin_count = max(1.0, float(np.sum(weight) ** 2 / np.sum(weight**2)) / smoothing)
    delay_se = (
        math.sqrt(residual_variance / max(frequency_information * effective_bin_count, 1e-30))
        * sample_rate_hz
        / (2 * np.pi)
    )
    # The bounded profile grid itself limits reported delay precision.
    delay_se = max(delay_se, float(delay_grid[1] - delay_grid[0]) / math.sqrt(12))
    phase_se = math.sqrt(residual_variance / effective_bin_count)
    transfer = smooth_cross[indexes] / np.maximum(smooth_power0[indexes], 1e-30)
    if channel_smoothing_bins > 1:
        kernel = np.ones(channel_smoothing_bins) / channel_smoothing_bins
        transfer = np.convolve(transfer, kernel, mode="same")
    model = BroadbandAlignmentModel(
        reference,
        frequency_center,
        cfo,
        rate_hz_s,
        delay,
        float(np.angle(np.exp(1j * intercept))),
        tuple(map(float, fft_frequency[indexes])),
        tuple(map(complex, transfer)),
        cfo_se,
        rate_se,
        delay_se,
        phase_se,
        "conditional_weighted_fit_scatter_not_calibrated_ci",
    )

    def validate(
        segment: np.ndarray, global_start: int, explicit_starts=None
    ) -> AlignmentValidation:
        local_starts = (
            np.arange(0, len(segment) - block_samples + 1, block_samples)
            if explicit_starts is None
            else explicit_starts
        )
        absolute = np.arange(global_start, global_start + len(segment), dtype=float)
        delta_s = (absolute - model.reference_sample) / sample_rate_hz
        rotation = np.exp(
            -2j
            * np.pi
            * (model.relative_cfo_hz * delta_s + 0.5 * model.relative_cfo_rate_hz_s * delta_s**2)
        )
        derotated = segment[:, 1] * rotation
        wrong_time = np.roll(derotated, max(1, len(segment) // 5 + 17))
        transfer = np.asarray(model.channel_transfer)
        predicted_parts, observed_parts, raw_parts, wrong_parts = [], [], [], []
        for i, start in enumerate(local_starts):
            left = np.fft.fftshift(np.fft.fft(segment[start : start + block_samples, 0] * window))[
                indexes
            ]
            observed = np.fft.fftshift(
                np.fft.fft(derotated[start : start + block_samples] * window)
            )[indexes]
            raw = np.fft.fftshift(np.fft.fft(segment[start : start + block_samples, 1] * window))[
                indexes
            ]
            wrong_values = wrong_time[start : start + block_samples]
            if explicit_starts is not None:
                wrong_start = local_starts[(i + max(1, len(local_starts) // 2)) % len(local_starts)]
                wrong_values = derotated[wrong_start : wrong_start + block_samples]
            wrong = np.fft.fftshift(np.fft.fft(wrong_values * window))[indexes]
            predicted_parts.append(transfer * left)
            observed_parts.append(observed)
            raw_parts.append(raw)
            wrong_parts.append(wrong)
        predicted = np.concatenate(predicted_parts)
        observed = np.concatenate(observed_parts)
        raw = np.concatenate(raw_parts)
        wrong = np.concatenate(wrong_parts)
        covered = len(indexes) * sample_rate_hz / block_samples
        denominator = math.sqrt(
            max(
                float(np.vdot(predicted, predicted).real * np.vdot(observed, observed).real),
                1e-30,
            )
        )
        normalized = np.vdot(predicted, observed) / denominator
        error = float(np.linalg.norm(observed - predicted)) / max(
            float(np.linalg.norm(observed)), 1e-30
        )
        return AlignmentValidation(
            _coherence(predicted, raw),
            float(abs(normalized)),
            _coherence(predicted, wrong),
            len(indexes),
            covered,
            float(np.angle(normalized)),
            float(normalized.real),
            float(error),
        )

    training_validation = (
        validate(train, 0) if selected_starts is None else validate(values, 0, selected_starts)
    )
    held_starts = (
        None
        if selected_starts is None
        else np.setdiff1d(
            np.arange(0, len(values) - block_samples + 1, block_samples), selected_starts
        )
    )
    if explicit_held_starts is not None:
        held_starts = explicit_held_starts
    held_validation = (
        validate(values[split:], split) if held_starts is None else validate(values, 0, held_starts)
    )
    return BroadbandAlignmentResult(
        model,
        training_validation,
        held_validation,
        tuple(map(float, fft_frequency)),
        tuple(map(float, bin_coherence)),
        tuple(map(float, np.angle(smooth_cross))),
        tuple(map(bool, physical_overlap)),
        tuple(map(float, time_s)),
        tuple(map(float, block_phase)),
    )
