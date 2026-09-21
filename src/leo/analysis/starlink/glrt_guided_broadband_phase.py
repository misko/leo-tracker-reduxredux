"""GLRT-guided MAP refinement of an observed dual-receiver broadband phase."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment


@dataclass(frozen=True, slots=True)
class GuidePoint:
    sample: float
    relative_frequency_hz: float
    sigma_hz: float


@dataclass(frozen=True, slots=True)
class GuidedPhaseModel:
    reference_sample: float
    frequency_reference_hz: float
    relative_cfo_hz: float
    relative_cfo_rate_hz_s: float
    effective_delay_samples: float
    observed_phase_rad: float
    parameter_covariance: tuple[tuple[float, ...], ...]
    parameter_covariance_order: tuple[str, str, str]
    conditional_phase_standard_error_rad: float
    guide_residual_hz: tuple[float, ...]
    inference_kind: str
    effective_spectral_group_count: float
    training_block_count: int
    guide_bias_hz: float
    phase_uncertainty_kind: str


@dataclass(frozen=True, slots=True)
class GuidedValidation:
    coherence: float
    phase_rad: float
    real_coherence: float
    wrong_time_coherence: float
    normalized_complex_error: float
    block_count: int


@dataclass(frozen=True, slots=True)
class GlrtGuidedBroadbandPhaseResult:
    data_only: GuidedPhaseModel
    map_model: GuidedPhaseModel
    training: GuidedValidation
    held_out: GuidedValidation
    data_only_training: GuidedValidation
    data_only_held_out: GuidedValidation
    selected_guide_count: int
    rejected_guide_count: int
    guide_symbol_branch_hz: tuple[float, ...]


def _fit_spectrum(
    values: np.ndarray,
    rate: float,
    cfo: float,
    drift: float,
    reference: float,
    split: int,
    block_samples: int,
    selected_frequency_hz: np.ndarray,
    frequency_reference_hz: float,
) -> tuple[float, float, float, float, float, int, np.ndarray, np.ndarray, np.ndarray]:
    window = np.hanning(block_samples)
    frequency = np.fft.fftshift(np.fft.fftfreq(block_samples, 1 / rate))
    cross = np.zeros(block_samples, complex)
    power0 = np.zeros(block_samples)
    power1 = np.zeros(block_samples)
    block_cross = []
    for start in range(0, split - block_samples + 1, block_samples):
        sample = np.arange(start, start + block_samples, dtype=float)
        time = (sample - reference) / rate
        rotation = np.exp(-2j * np.pi * (cfo * time + 0.5 * drift * time**2))
        left = np.fft.fftshift(np.fft.fft(values[start : start + block_samples, 0] * window))
        right = np.fft.fftshift(
            np.fft.fft(values[start : start + block_samples, 1] * rotation * window)
        )
        current_cross = right * np.conj(left)
        cross += current_cross
        block_cross.append(current_cross)
        power0 += abs(left) ** 2
        power1 += abs(right) ** 2
    kernel = np.ones(31) / 31
    cross = np.convolve(cross, kernel, mode="same")
    power0 = np.convolve(power0, kernel, mode="same")
    power1 = np.convolve(power1, kernel, mode="same")
    indexes = np.searchsorted(frequency, selected_frequency_hz)
    if np.any(indexes >= len(frequency)) or not np.allclose(
        frequency[indexes], selected_frequency_hz, atol=1e-6
    ):
        raise ValueError("frozen broadband mask does not match guided FFT grid")
    if len(indexes) < 16:
        raise ValueError("insufficient coherent broadband support")
    weight = np.minimum(abs(cross[indexes]), np.percentile(abs(cross[indexes]), 90))
    center = float(frequency_reference_hz)
    centered = frequency[indexes] - center
    phase = np.angle(cross[indexes])
    grid = np.linspace(-8, 8, 1601)
    scores = np.asarray(
        [abs(np.sum(weight * np.exp(1j * phase + 2j * np.pi * centered * d / rate))) for d in grid]
    )
    delay = float(grid[int(np.argmax(scores))])
    corrected = np.exp(1j * phase + 2j * np.pi * centered * delay / rate)
    observed_phase = float(np.angle(np.sum(weight * corrected)))
    residual = np.angle(corrected * np.exp(-1j * observed_phase))
    effective_groups = max(1.0, float(np.sum(weight) ** 2 / max(np.sum(weight**2), 1e-30)) / 31)
    phase_se = math.sqrt(float(np.average(residual**2, weights=weight)) / effective_groups)
    block_phasor = np.asarray(
        [
            np.sum(
                weight
                * np.convolve(item, kernel, mode="same")[indexes]
                / np.maximum(abs(np.convolve(item, kernel, mode="same")[indexes]), 1e-30)
                * np.exp(2j * np.pi * centered * delay / rate)
            )
            for item in block_cross
        ]
    )
    groups = [group for group in np.array_split(np.arange(len(block_phasor)), 4) if len(group)]
    if len(groups) > 1:
        total = np.sum(block_phasor)
        leave_group_phase = np.asarray(
            [np.angle(total - np.sum(block_phasor[group])) for group in groups]
        )
        center_phase = float(np.angle(np.sum(np.exp(1j * leave_group_phase))))
        differences = np.angle(np.exp(1j * (leave_group_phase - center_phase)))
        jackknife_se = math.sqrt((len(groups) - 1) / len(groups) * float(np.sum(differences**2)))
        phase_se = max(phase_se, jackknife_se)
    transfer = cross[indexes] / np.maximum(power0[indexes], 1e-30)
    return (
        center,
        delay,
        observed_phase,
        phase_se,
        effective_groups,
        len(block_cross),
        frequency[indexes],
        transfer,
        indexes,
    )


def estimate_glrt_guided_broadband_phase(
    iq: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    guides: tuple[GuidePoint, ...] | list[GuidePoint],
    *,
    broadband_cfo_seed_hz: float,
    cfo_search_half_width_hz: float = 2_000.0,
    training_fraction: float = 0.5,
    block_samples: int = 4096,
    reference_sample: float | None = None,
    fit_guide_bias: bool = False,
) -> GlrtGuidedBroadbandPhaseResult:
    """Combine training-only GLRT frequencies with the broadband likelihood."""
    values = np.asarray(iq)
    split = int(len(values) * training_fraction)
    alignment = estimate_broadband_alignment(
        values,
        sample_rate_hz,
        receiver_cfo_seed_hz=broadband_cfo_seed_hz,
        cfo_search_half_width_hz=cfo_search_half_width_hz,
        training_fraction=training_fraction,
        block_samples=block_samples,
    )
    data = alignment.model
    reference = data.reference_sample if reference_sample is None else float(reference_sample)
    selected = [
        g
        for g in guides
        if all(math.isfinite(value) for value in (g.sample, g.relative_frequency_hz, g.sigma_hz))
        and 0 <= g.sample < split
        and g.sigma_hz > 0
    ]
    if not selected:
        raise ValueError("no finite positive-uncertainty guide lies in training partition")
    alias = 1 / 4.4e-6
    lifted = np.asarray(
        [
            g.relative_frequency_hz
            + round((data.relative_cfo_hz - g.relative_frequency_hz) / alias) * alias
            for g in selected
        ]
    )
    guide_time = (np.asarray([g.sample for g in selected]) - reference) / sample_rate_hz
    design = np.column_stack((np.ones(len(selected)), guide_time))
    fit_design = np.column_stack((design, np.ones(len(selected)))) if fit_guide_bias else design
    sigma = np.asarray([g.sigma_hz for g in selected])
    precision = fit_design.T @ ((1 / sigma**2)[:, None] * fit_design)
    rhs = fit_design.T @ (lifted / sigma**2)
    prior_sigma = np.asarray(
        [
            max(data.relative_cfo_standard_error_hz, 0.1),
            max(data.relative_cfo_rate_standard_error_hz_s, 1.0),
        ]
    )
    prior_mean = np.asarray(
        [
            data.relative_cfo_hz
            + data.relative_cfo_rate_hz_s * (reference - data.reference_sample) / sample_rate_hz,
            data.relative_cfo_rate_hz_s,
        ]
    )
    fit_prior_sigma = np.append(prior_sigma, 10_000.0) if fit_guide_bias else prior_sigma
    fit_prior_mean = np.append(prior_mean, 0.0) if fit_guide_bias else prior_mean
    precision += np.diag(1 / fit_prior_sigma**2)
    rhs += fit_prior_mean / fit_prior_sigma**2
    covariance = np.linalg.inv(precision)
    fitted = covariance @ rhs
    map_frequency, map_drift = fitted[:2]
    guide_bias = float(fitted[2]) if fit_guide_bias else 0.0
    guide_residual = lifted - fit_design @ fitted
    robust = abs(guide_residual) <= np.maximum(4 * sigma, 50.0)
    if np.sum(robust) >= 2 and not np.all(robust):
        kept_design, kept_sigma, kept_lifted = (
            fit_design[robust],
            sigma[robust],
            lifted[robust],
        )
        precision = kept_design.T @ ((1 / kept_sigma**2)[:, None] * kept_design) + np.diag(
            1 / fit_prior_sigma**2
        )
        rhs = kept_design.T @ (kept_lifted / kept_sigma**2) + fit_prior_mean / fit_prior_sigma**2
        covariance = np.linalg.inv(precision)
        fitted = covariance @ rhs
        map_frequency, map_drift = fitted[:2]
        guide_bias = float(fitted[2]) if fit_guide_bias else 0.0
        guide_residual = lifted - fit_design @ fitted
    elif not np.all(robust):
        map_frequency, map_drift = prior_mean
        covariance = np.diag(prior_sigma**2)
        guide_bias = 0.0
        robust[:] = False
        guide_residual = lifted - design @ prior_mean

    frozen_frequency = np.asarray(data.frequency_hz)
    endpoint_times = (np.asarray((0.0, len(values) - 1.0)) - reference) / sample_rate_hz
    for endpoint_cfo in map_frequency + map_drift * endpoint_times:
        if np.any(abs(frozen_frequency + endpoint_cfo) >= sample_rate_hz / 2):
            raise ValueError("guided trajectory leaves the recorded common bandwidth")
    common_frequency_reference = data.frequency_reference_hz
    (
        data_center,
        data_delay,
        data_phase,
        data_phase_se,
        data_effective_groups,
        data_block_count,
        _,
        data_transfer,
        data_indexes,
    ) = _fit_spectrum(
        values,
        sample_rate_hz,
        prior_mean[0],
        prior_mean[1],
        reference,
        split,
        block_samples,
        frozen_frequency,
        common_frequency_reference,
    )
    (
        map_center,
        map_delay,
        map_phase,
        map_phase_se,
        map_effective_groups,
        map_block_count,
        bins,
        transfer,
        indexes,
    ) = _fit_spectrum(
        values,
        sample_rate_hz,
        map_frequency,
        map_drift,
        reference,
        split,
        block_samples,
        frozen_frequency,
        common_frequency_reference,
    )

    def model(
        kind: str,
        cfo: float,
        drift: float,
        center: float,
        delay: float,
        phase: float,
        covariance_values: np.ndarray,
        residual_values: np.ndarray,
        effective_groups: float,
        training_block_count: int,
        fitted_guide_bias: float,
    ) -> GuidedPhaseModel:
        return GuidedPhaseModel(
            reference,
            center,
            float(cfo),
            float(drift),
            delay,
            phase,
            tuple(tuple(map(float, row)) for row in covariance_values),
            ("relative_cfo_hz", "relative_cfo_rate_hz_s", "observed_phase_rad"),
            float(math.sqrt(max(covariance_values[2, 2], 0))),
            tuple(map(float, residual_values)),
            kind,
            effective_groups,
            training_block_count,
            fitted_guide_bias,
            "max_frozen_spectral_scatter_and_four_contiguous_group_delete_jackknife_not_total_ci",
        )

    data_cov = np.diag((prior_sigma[0] ** 2, prior_sigma[1] ** 2, data_phase_se**2))
    map_cov = np.zeros((3, 3))
    map_cov[:2, :2] = covariance[:2, :2]
    map_cov[2, 2] = map_phase_se**2

    def validate(
        start: int,
        stop: int,
        fitted_cfo: float,
        fitted_drift: float,
        fitted_transfer: np.ndarray,
        fitted_indexes: np.ndarray,
    ) -> GuidedValidation:
        window = np.hanning(block_samples)
        predicted_all = []
        observed_all = []
        wrong_all = []
        for block in range(start, stop - block_samples + 1, block_samples):
            sample = np.arange(block, block + block_samples, dtype=float)
            time = (sample - reference) / sample_rate_hz
            rotation = np.exp(-2j * np.pi * (fitted_cfo * time + 0.5 * fitted_drift * time**2))
            left = np.fft.fftshift(np.fft.fft(values[block : block + block_samples, 0] * window))[
                fitted_indexes
            ]
            right = np.fft.fftshift(
                np.fft.fft(values[block : block + block_samples, 1] * rotation * window)
            )[fitted_indexes]
            predicted_all.append(fitted_transfer * left)
            observed_all.append(right)
            wrong_start = start + (block - start + (stop - start) // 3 + 17) % max(
                stop - start - block_samples + 1, 1
            )
            wrong_sample = np.arange(wrong_start, wrong_start + block_samples, dtype=float)
            wrong_time = (wrong_sample - reference) / sample_rate_hz
            wrong_rotation = np.exp(
                -2j * np.pi * (fitted_cfo * wrong_time + 0.5 * fitted_drift * wrong_time**2)
            )
            wrong = np.fft.fftshift(
                np.fft.fft(
                    values[wrong_start : wrong_start + block_samples, 1] * wrong_rotation * window
                )
            )[fitted_indexes]
            wrong_all.append(wrong)
        predicted = np.concatenate(predicted_all)
        observed = np.concatenate(observed_all)
        wrong = np.concatenate(wrong_all)
        cross = np.vdot(predicted, observed)
        den = math.sqrt(
            max(float(np.vdot(predicted, predicted).real * np.vdot(observed, observed).real), 1e-30)
        )
        return GuidedValidation(
            float(abs(cross) / den),
            float(np.angle(cross)),
            float(cross.real / den),
            float(
                abs(np.vdot(predicted, wrong))
                / math.sqrt(
                    max(
                        float(np.vdot(predicted, predicted).real * np.vdot(wrong, wrong).real),
                        1e-30,
                    )
                )
            ),
            float(np.linalg.norm(observed - predicted) / np.linalg.norm(observed)),
            len(predicted_all),
        )

    return GlrtGuidedBroadbandPhaseResult(
        model(
            "broadband_data_only",
            prior_mean[0],
            prior_mean[1],
            data_center,
            data_delay,
            data_phase,
            data_cov,
            lifted - design @ prior_mean,
            data_effective_groups,
            data_block_count,
            0.0,
        ),
        model(
            "conditional_composite_guide_penalized_map_same_iq_not_independent_posterior",
            map_frequency,
            map_drift,
            map_center,
            map_delay,
            map_phase,
            map_cov,
            guide_residual,
            map_effective_groups,
            map_block_count,
            guide_bias,
        ),
        validate(0, split, map_frequency, map_drift, transfer, indexes),
        validate(split, len(values), map_frequency, map_drift, transfer, indexes),
        validate(0, split, prior_mean[0], prior_mean[1], data_transfer, data_indexes),
        validate(
            split,
            len(values),
            prior_mean[0],
            prior_mean[1],
            data_transfer,
            data_indexes,
        ),
        int(np.sum(robust)),
        len(selected) - int(np.sum(robust)),
        tuple(map(float, lifted)),
    )
