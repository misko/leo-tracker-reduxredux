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
) -> BroadbandAlignmentResult:
    """Fit on the first time partition and validate unchanged on the second.

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
        candidate_spectrum = np.fft.fftshift(
            np.fft.fft(candidate_product * np.hanning(len(candidate_product)), size)
        )
        score = float(np.max(abs(candidate_spectrum[bounded])))
        if best is None or score > best[0]:
            best = (score, lag, candidate_product, candidate_spectrum)
    assert best is not None
    _, integer_delay, product, spectrum = best
    coarse = float(frequencies[np.flatnonzero(bounded)[np.argmax(abs(spectrum[bounded]))]])

    starts = np.arange(0, len(product) - block_samples + 1, block_samples)
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
    block_phase = np.unwrap(np.angle(block_phasor))
    coefficients = _robust_polynomial(time_s, block_phase, abs(block_phasor))
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

    time_design = np.column_stack((np.ones(len(time_s)), time_s, 0.5 * time_s**2))
    time_residual = np.unwrap(np.angle(block_phasor)) - time_design @ coefficients
    time_covariance = np.linalg.pinv(time_design.T @ time_design) * float(
        np.sum(time_residual**2) / max(len(time_s) - 3, 1)
    )
    cfo_se = math.sqrt(max(float(time_covariance[1, 1]), 0.0)) / (2 * np.pi)
    rate_se = math.sqrt(max(float(time_covariance[2, 2]), 0.0)) / (2 * np.pi)
    leave_chunk_parameters = []
    for omitted in np.array_split(np.arange(len(time_s)), min(4, len(time_s))):
        retained = np.ones(len(time_s), dtype=bool)
        retained[omitted] = False
        if np.sum(retained) < 3:
            continue
        if quadratic_selected:
            refit = _robust_polynomial(
                time_s[retained], block_phase[retained], abs(block_phasor[retained])
            )
        else:
            design = np.column_stack((np.ones(np.sum(retained)), time_s[retained]))
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

    def validate(segment: np.ndarray, global_start: int) -> AlignmentValidation:
        local_starts = np.arange(0, len(segment) - block_samples + 1, block_samples)
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
        for start in local_starts:
            left = np.fft.fftshift(np.fft.fft(segment[start : start + block_samples, 0] * window))[
                indexes
            ]
            observed = np.fft.fftshift(
                np.fft.fft(derotated[start : start + block_samples] * window)
            )[indexes]
            raw = np.fft.fftshift(np.fft.fft(segment[start : start + block_samples, 1] * window))[
                indexes
            ]
            wrong = np.fft.fftshift(np.fft.fft(wrong_time[start : start + block_samples] * window))[
                indexes
            ]
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

    return BroadbandAlignmentResult(
        model,
        validate(train, 0),
        validate(values[split:], split),
        tuple(map(float, fft_frequency)),
        tuple(map(float, bin_coherence)),
        tuple(map(float, np.angle(smooth_cross))),
        tuple(map(bool, physical_overlap)),
        tuple(map(float, time_s)),
        tuple(map(float, np.unwrap(np.angle(block_phasor)))),
    )
