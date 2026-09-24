#!/usr/bin/env python3
"""Bounded raw-IQ validation of a dual-RX frequency and phase branch.

This research tool reads only selected, immutable adaptive visits.  It derives
an RX1-minus-RX0 broadband frequency authority from the first half of each
visit, validates it on the held-out second half, and then re-correlates both
pilot receivers with one common CFO branch and sample reference.  Published
phase V2 products are never modified.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import numpy.typing as npt

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink.adaptive_dual_rx_phase import (  # noqa: E402
    SYMBOL_ALIAS_HZ,
    circular_frequency_delta,
)
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (  # noqa: E402
    DualReceiverPhaseObservation,
    ReceiverPhaseSeed,
    extract_dual_receiver_phase_with_offset_authority,
)
from leo.application.adaptive_dual_rx_phase_v2 import (  # noqa: E402
    _extract_pair,
    _phase_blind_pairs,
)
from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.scanner.adaptive_hop_analysis import (  # noqa: E402
    AdaptiveHopAnalysisConfigurationV1,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore  # noqa: E402

DEFAULT_VISITS = (
    1065,
    1069,
    1073,
    1077,
    1081,
    1085,
    1089,
    1093,
    1097,
    1101,
    1105,
    1109,
    1113,
    1117,
    1120,
    1124,
    1128,
    1132,
    1136,
    1140,
)
FRAME_RATE_HZ = 750.0


@dataclass(frozen=True, slots=True)
class AmbiguityPeak:
    frequency_hz: float
    delay_samples: int
    coherence: float


@dataclass(frozen=True, slots=True)
class SubbandTransfer:
    coherence: float
    phase_deg: float
    phase_at_center_deg: float
    fractional_delay_samples: float
    phase_slope_resultant: float
    fractional_delay_alias_period_samples: float


def _aligned(values: npt.NDArray[np.complexfloating], delay: int) -> tuple[np.ndarray, np.ndarray]:
    if delay >= 0:
        return values[: len(values) - delay or None, 0], values[delay:, 1]
    return values[-delay:, 0], values[: len(values) + delay, 1]


def coherence_at(
    values: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    frequency_hz: float,
    delay_samples: int,
) -> float:
    """Symmetrically normalized complex cross-coherence at one CFO and delay."""
    left, right = _aligned(np.asarray(values), delay_samples)
    window = np.hanning(len(left))
    time = np.arange(len(left), dtype=float) / sample_rate_hz
    numerator = abs(
        np.sum(window * right * np.conj(left) * np.exp(-2j * np.pi * frequency_hz * time))
    )
    denominator = math.sqrt(
        float(np.sum(window * abs(left) ** 2)) * float(np.sum(window * abs(right) ** 2))
    )
    return float(numerator / max(denominator, np.finfo(float).tiny))


def coherence_phasor_at(
    values: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    frequency_hz: float,
    delay_samples: int,
) -> complex:
    """Return normalized complex cross-coherence, retaining its phase."""
    left, right = _aligned(np.asarray(values), delay_samples)
    window = np.hanning(len(left))
    time = np.arange(len(left), dtype=float) / sample_rate_hz
    numerator = np.sum(window * right * np.conj(left) * np.exp(-2j * np.pi * frequency_hz * time))
    denominator = math.sqrt(
        float(np.sum(window * abs(left) ** 2)) * float(np.sum(window * abs(right) ** 2))
    )
    return complex(numerator / max(denominator, np.finfo(float).tiny))


def cross_ambiguity_peak(
    values: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    *,
    minimum_frequency_hz: float = -900_000.0,
    maximum_frequency_hz: float = -300_000.0,
    maximum_delay_samples: int = 0,
) -> AmbiguityPeak:
    """Find the normalized wideband RX product peak in a bounded search."""
    if (
        values.ndim != 2
        or values.shape[1] != 2
        or not np.iscomplexobj(values)
        or not math.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0
        or not minimum_frequency_hz < maximum_frequency_hz
        or not 0 <= maximum_delay_samples <= 32
    ):
        raise ValueError("invalid cross-ambiguity input")
    best: AmbiguityPeak | None = None
    for delay in range(-maximum_delay_samples, maximum_delay_samples + 1):
        left, right = _aligned(values, delay)
        window = np.hanning(len(left))
        product = window * right * np.conj(left)
        size = 1 << math.ceil(math.log2(len(product)))
        spectrum = np.fft.fftshift(np.fft.fft(product, n=size))
        frequencies = np.fft.fftshift(np.fft.fftfreq(size, 1 / sample_rate_hz))
        bounded = np.flatnonzero(
            (frequencies >= minimum_frequency_hz) & (frequencies <= maximum_frequency_hz)
        )
        peak_index = int(bounded[np.argmax(abs(spectrum[bounded]))])
        offset = 0.0
        if 0 < peak_index < size - 1:
            three = np.log(np.maximum(abs(spectrum[peak_index - 1 : peak_index + 2]), 1e-300))
            denominator = three[0] - 2 * three[1] + three[2]
            if denominator != 0:
                offset = float(0.5 * (three[0] - three[2]) / denominator)
        frequency = float(frequencies[peak_index] + offset * sample_rate_hz / size)
        score = coherence_at(values, sample_rate_hz, frequency, delay)
        candidate = AmbiguityPeak(frequency, delay, score)
        if best is None or candidate.coherence > best.coherence:
            best = candidate
    assert best is not None
    return best


def subband_transfer(
    values: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    receiver_offset_hz: float,
    rx0_center_hz: float,
    *,
    rx1_aligned_center_hz: float | None = None,
    global_start_sample: int = 0,
    block_samples: int = 8192,
    half_width_hz: float = 6_000.0,
) -> SubbandTransfer:
    """Estimate an IQ waveform transfer in one narrow, phase-blind subband."""
    if len(values) < block_samples or block_samples < 256 or half_width_hz <= 0:
        raise ValueError("invalid subband transfer input")
    rx1_center = rx0_center_hz if rx1_aligned_center_hz is None else rx1_aligned_center_hz
    absolute_sample = np.arange(len(values), dtype=float) + global_start_sample
    rx0 = np.asarray(values[:, 0], np.complex128)
    rx1 = np.asarray(values[:, 1], np.complex128) * np.exp(
        -2j * np.pi * receiver_offset_hz * absolute_sample / sample_rate_hz
    )
    frequency = np.fft.fftshift(np.fft.fftfreq(block_samples, 1 / sample_rate_hz))
    radius = max(1, int(half_width_hz / (sample_rate_hz / block_samples)))
    center0 = int(np.argmin(abs(frequency - rx0_center_hz)))
    center1 = int(np.argmin(abs(frequency - rx1_center)))
    indexes0 = np.arange(center0 - radius, center0 + radius + 1)
    indexes1 = np.arange(center1 - radius, center1 + radius + 1)
    if min(indexes0[0], indexes1[0]) < 0 or max(indexes0[-1], indexes1[-1]) >= block_samples:
        raise ValueError("subband transfer window leaves sampled spectrum")
    window = np.hanning(block_samples)
    cross_by_bin = np.zeros(len(indexes0), dtype=np.complex128)
    power0_by_bin = np.zeros(len(indexes0))
    power1_by_bin = np.zeros(len(indexes0))
    for start in range(0, len(values) - block_samples + 1, block_samples):
        spectrum0 = np.fft.fftshift(np.fft.fft(rx0[start : start + block_samples] * window))
        spectrum1 = np.fft.fftshift(np.fft.fft(rx1[start : start + block_samples] * window))
        selected0 = spectrum0[indexes0]
        selected1 = spectrum1[indexes1]
        cross_by_bin += selected1 * np.conj(selected0)
        power0_by_bin += abs(selected0) ** 2
        power1_by_bin += abs(selected1) ** 2
    cross = complex(np.sum(cross_by_bin))
    power0 = float(np.sum(power0_by_bin))
    power1 = float(np.sum(power1_by_bin))
    coherence = abs(cross) / math.sqrt(max(power0 * power1, np.finfo(float).tiny))
    selected_frequency = frequency[indexes0]
    weights = abs(cross_by_bin)
    phases = np.unwrap(np.angle(cross_by_bin))
    reference_hz = float(np.average(selected_frequency, weights=weights))
    design = np.column_stack((selected_frequency - reference_hz, np.ones(len(phases))))
    slope, intercept = np.linalg.lstsq(
        design * np.sqrt(weights)[:, None], phases * np.sqrt(weights), rcond=None
    )[0]
    center_phase = intercept + slope * (rx0_center_hz - reference_hz)
    fractional_delay = -float(slope) * sample_rate_hz / (2 * np.pi)
    residual = phases - design @ np.asarray((slope, intercept))
    phase_slope_resultant = abs(np.sum(weights * np.exp(1j * residual))) / np.sum(weights)
    return SubbandTransfer(
        float(coherence),
        math.degrees(float(np.angle(cross))),
        math.degrees(float(np.angle(np.exp(1j * center_phase)))),
        fractional_delay,
        float(phase_slope_resultant),
        sample_rate_hz / (2 * half_width_hz),
    )


def _subband_evidence(
    iq: np.ndarray,
    sample_rate_hz: float,
    receiver_offset_hz: float,
    pairs: list[Any],
) -> list[dict[str, Any]]:
    midpoint = len(iq) // 2
    output = []
    for index, pair in enumerate(pairs):
        center = pair[0].fractional_tracking_cfo_hz
        wrong_center = (
            pairs[(index + 1) % len(pairs)][0].fractional_tracking_cfo_hz
            if len(pairs) > 1
            else center + 50_000.0
        )
        output.append(
            {
                "rx0_center_hz": center,
                "first_60ms": asdict(
                    subband_transfer(iq[:midpoint], sample_rate_hz, receiver_offset_hz, center)
                ),
                "held_second_60ms": asdict(
                    subband_transfer(
                        iq[midpoint:],
                        sample_rate_hz,
                        receiver_offset_hz,
                        center,
                        global_start_sample=midpoint,
                    )
                ),
                "wrong_source_first_60ms": asdict(
                    subband_transfer(
                        iq[:midpoint],
                        sample_rate_hz,
                        receiver_offset_hz,
                        center,
                        rx1_aligned_center_hz=wrong_center,
                    )
                ),
            }
        )
    return output


def remove_common_phase_nuisance(
    values: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    receiver_offset_hz: float,
    excluded_centers_hz: tuple[float, ...],
    *,
    block_samples: int = 5_000,
    exclusion_half_width_hz: float = 10_000.0,
    smoothing_radius_blocks: int = 2,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Remove a shared RX phase track estimated outside target subbands."""
    if (
        values.ndim != 2
        or values.shape[1] != 2
        or len(values) < 3 * block_samples
        or block_samples < 256
        or not excluded_centers_hz
        or exclusion_half_width_hz <= 0
        or not 0 <= smoothing_radius_blocks <= 8
    ):
        raise ValueError("invalid common phase nuisance input")
    sample = np.arange(len(values), dtype=float)
    aligned_rx1 = np.asarray(values[:, 1], np.complex128) * np.exp(
        -2j * np.pi * receiver_offset_hz * sample / sample_rate_hz
    )
    rx0 = np.asarray(values[:, 0], np.complex128)
    window = np.hanning(block_samples)
    frequencies = np.fft.fftshift(np.fft.fftfreq(block_samples, 1 / sample_rate_hz))
    retained = np.ones(block_samples, dtype=bool)
    for center in excluded_centers_hz:
        retained &= abs(frequencies - center) > exclusion_half_width_hz
    centers = []
    phase = []
    coherence = []
    for start in range(0, len(values) - block_samples + 1, block_samples):
        spectrum0 = np.fft.fftshift(np.fft.fft(rx0[start : start + block_samples] * window))[
            retained
        ]
        spectrum1 = np.fft.fftshift(
            np.fft.fft(aligned_rx1[start : start + block_samples] * window)
        )[retained]
        cross = complex(np.sum(spectrum1 * np.conj(spectrum0)))
        denominator = math.sqrt(
            float(np.sum(abs(spectrum0) ** 2)) * float(np.sum(abs(spectrum1) ** 2))
        )
        centers.append(start + (block_samples - 1) / 2)
        phase.append(float(np.angle(cross)))
        coherence.append(abs(cross) / max(denominator, np.finfo(float).tiny))
    unwrapped = np.unwrap(phase)
    coherence_array = np.asarray(coherence)
    smoothed = []
    for index in range(len(unwrapped)):
        selected = slice(
            max(0, index - smoothing_radius_blocks),
            min(len(unwrapped), index + smoothing_radius_blocks + 1),
        )
        weights = coherence_array[selected] ** 2
        smoothed.append(float(np.average(unwrapped[selected], weights=weights)))
    smoothed_array = np.unwrap(smoothed)
    curve = np.interp(
        sample,
        np.asarray(centers),
        smoothed_array,
        left=smoothed_array[0],
        right=smoothed_array[-1],
    )
    curve -= smoothed_array[0]
    corrected = np.array(values, dtype=np.complex128, copy=True)
    corrected[:, 1] *= np.exp(-1j * curve)
    return corrected, {
        "block_samples": block_samples,
        "block_duration_ms": 1_000 * block_samples / sample_rate_hz,
        "block_count": len(centers),
        "excluded_centers_hz": list(excluded_centers_hz),
        "exclusion_half_width_hz": exclusion_half_width_hz,
        "smoothing_radius_blocks": smoothing_radius_blocks,
        "coherence_median": float(np.median(coherence_array)),
        "coherence_minimum": float(np.min(coherence_array)),
        "coherence_maximum": float(np.max(coherence_array)),
        "smoothed_phase_span_deg": math.degrees(
            float(np.max(smoothed_array) - np.min(smoothed_array))
        ),
        "absolute_phase_reference": "first_smoothed_block_arbitrary_zero",
        "target_bands_used_for_nuisance": False,
    }


def source_overlap_evidence(
    values: npt.NDArray[np.complexfloating],
    sample_rate_hz: float,
    receiver_offset_hz: float,
    centers_hz: tuple[float, float],
    *,
    block_ms: int = 20,
    minimum_coherence: float = 0.10,
    minimum_wrong_source_ratio: float = 2.0,
) -> dict[str, Any]:
    """Gate a two-source phase difference on simultaneous same-waveform support."""
    block_samples = round(sample_rate_hz * block_ms / 1_000)
    transfer_block_samples = min(8192, 1 << math.floor(math.log2(block_samples)))
    rows = []
    for start in range(0, len(values) - block_samples + 1, block_samples):
        sources = []
        for index, center in enumerate(centers_hz):
            matched = subband_transfer(
                values[start : start + block_samples],
                sample_rate_hz,
                receiver_offset_hz,
                center,
                global_start_sample=start,
                block_samples=transfer_block_samples,
            )
            wrong = subband_transfer(
                values[start : start + block_samples],
                sample_rate_hz,
                receiver_offset_hz,
                center,
                rx1_aligned_center_hz=centers_hz[1 - index],
                global_start_sample=start,
                block_samples=transfer_block_samples,
            )
            qualified = (
                matched.coherence >= minimum_coherence
                and matched.coherence
                >= minimum_wrong_source_ratio * max(wrong.coherence, np.finfo(float).tiny)
            )
            sources.append(
                {
                    "center_hz": center,
                    "matched": asdict(matched),
                    "wrong_source": asdict(wrong),
                    "qualified": qualified,
                }
            )
        overlap = all(source["qualified"] for source in sources)
        phase = None
        if overlap:
            phase = _phase_error_deg(
                math.radians(sources[1]["matched"]["phase_deg"]),
                math.radians(sources[0]["matched"]["phase_deg"]),
            )
        rows.append(
            {
                "start_ms": 1_000 * start / sample_rate_hz,
                "sources": sources,
                "both_sources_qualified": overlap,
                "wrapped_high_minus_low_phase_deg": phase,
            }
        )
    return {
        "block_ms": block_ms,
        "transfer_fft_samples": transfer_block_samples,
        "subband_half_width_hz": 6_000.0,
        "approximate_time_bandwidth_product_per_source": 2 * 6_000.0 * block_ms / 1_000,
        "minimum_coherence": minimum_coherence,
        "minimum_matched_to_wrong_source_ratio": minimum_wrong_source_ratio,
        "gate_uses_phase": False,
        "qualified_overlap_block_count": sum(row["both_sources_qualified"] for row in rows),
        "total_block_count": len(rows),
        "blocks": rows,
    }


def _phase_at(observation: DualReceiverPhaseObservation, sample: float, rate: float) -> float:
    return float(
        np.angle(
            np.exp(
                1j
                * (
                    observation.wrapped_phase_rad
                    + 2
                    * np.pi
                    * observation.relative_frequency_hz
                    * (sample - observation.center_sample)
                    / rate
                )
            )
        )
    )


def _phase_error_deg(left: float, right: float) -> float:
    return math.degrees(float(np.angle(np.exp(1j * (left - right)))))


def _correct_pair(iq: np.ndarray, visit: Any, pair: Any, offset_hz: float) -> dict[str, Any] | None:
    left, right, _, probe_start_samples = pair
    references = tuple(
        probe_start_samples
        + candidate.integer_epoch_sample
        + candidate.fractional_epoch_offset_samples
        for candidate in (left, right)
    )
    seeds = (
        ReceiverPhaseSeed(left.acquired_cfo_hz, references[0]),
        ReceiverPhaseSeed(right.acquired_cfo_hz, references[1]),
    )
    frame_epoch = probe_start_samples + left.integer_epoch_sample
    reference = references[0]
    bound = extract_dual_receiver_phase_with_offset_authority(
        iq,
        visit.configuration.sample_rate_hz,
        visit.target.edge,
        frame_epoch,
        seeds,
        offset_hz,
        common_reference_sample=reference,
    )
    observation = bound.observation
    if (
        observation.resultant_length < 0.5
        or min(row.exact_to_control_power_ratio for row in observation.receivers) < 2.0
    ):
        return None

    fixed_sample = observation.center_sample
    shifted_reference = extract_dual_receiver_phase_with_offset_authority(
        iq,
        visit.configuration.sample_rate_hz,
        visit.target.edge,
        frame_epoch,
        seeds,
        offset_hz,
        common_reference_sample=reference + 997.0,
    ).observation
    shifted_alias = (
        ReceiverPhaseSeed(left.acquired_cfo_hz + SYMBOL_ALIAS_HZ, references[0]),
        ReceiverPhaseSeed(right.acquired_cfo_hz, references[1]),
    )
    common_alias = extract_dual_receiver_phase_with_offset_authority(
        iq,
        visit.configuration.sample_rate_hz,
        visit.target.edge,
        frame_epoch,
        shifted_alias,
        offset_hz,
        common_reference_sample=reference,
    ).observation
    first_symbols = extract_dual_receiver_phase_with_offset_authority(
        iq,
        visit.configuration.sample_rate_hz,
        visit.target.edge,
        frame_epoch,
        seeds,
        offset_hz,
        common_reference_sample=reference,
        symbol_indices=np.arange(2, 34),
    ).observation
    second_symbols = extract_dual_receiver_phase_with_offset_authority(
        iq,
        visit.configuration.sample_rate_hz,
        visit.target.edge,
        frame_epoch,
        seeds,
        offset_hz,
        common_reference_sample=reference,
        symbol_indices=np.arange(34, 66),
    ).observation
    legacy = _extract_pair(iq, visit, pair)
    return {
        "rx0_tracking_cfo_hz": left.fractional_tracking_cfo_hz,
        "rx1_tracking_cfo_hz": right.fractional_tracking_cfo_hz,
        "rx0_acquired_cfo_hz": left.acquired_cfo_hz,
        "rx1_original_acquired_cfo_hz": right.acquired_cfo_hz,
        "rx1_applied_acquired_cfo_hz": bound.applied_seeds[1].acquired_cfo_hz,
        "center_sample": observation.center_sample,
        "phase_rad": observation.wrapped_phase_rad,
        "relative_frequency_hz": observation.relative_frequency_hz,
        "relative_frequency_standard_error_hz": observation.relative_frequency_standard_error_hz,
        "resultant_length": observation.resultant_length,
        "phase_standard_error_deg": observation.phase_standard_error_deg,
        "exact_to_control_power_ratio_floor": min(
            row.exact_to_control_power_ratio for row in observation.receivers
        ),
        "legacy_phase_rad": None if legacy is None else legacy.wrapped_phase_rad,
        "legacy_relative_frequency_hz": None if legacy is None else legacy.relative_frequency_hz,
        "controls": {
            "common_reference_shift_phase_error_deg": _phase_error_deg(
                _phase_at(shifted_reference, fixed_sample, visit.configuration.sample_rate_hz),
                _phase_at(observation, fixed_sample, visit.configuration.sample_rate_hz),
            ),
            "common_symbol_alias_phase_error_deg": _phase_error_deg(
                _phase_at(common_alias, fixed_sample, visit.configuration.sample_rate_hz),
                _phase_at(observation, fixed_sample, visit.configuration.sample_rate_hz),
            ),
            "contiguous_symbol_halves_phase_error_deg": _phase_error_deg(
                _phase_at(first_symbols, fixed_sample, visit.configuration.sample_rate_hz),
                _phase_at(second_symbols, fixed_sample, visit.configuration.sample_rate_hz),
            ),
            "common_symbol_alias_resultant": common_alias.resultant_length,
            "common_symbol_alias_exact_to_control_floor": min(
                row.exact_to_control_power_ratio for row in common_alias.receivers
            ),
            "first_symbol_half_resultant": first_symbols.resultant_length,
            "second_symbol_half_resultant": second_symbols.resultant_length,
            "first_symbol_half_exact_to_control_floor": min(
                row.exact_to_control_power_ratio for row in first_symbols.receivers
            ),
            "second_symbol_half_exact_to_control_floor": min(
                row.exact_to_control_power_ratio for row in second_symbols.receivers
            ),
        },
    }


def _double_differences(
    visit: Any, pairs: list[Any], results: list[dict[str, Any] | None], offset: float
) -> list[dict[str, Any]]:
    qualified = [(pair, row) for pair, row in zip(pairs, results, strict=True) if row is not None]
    output: list[dict[str, Any]] = []
    rate = visit.configuration.sample_rate_hz
    origin = (visit.valid_start_counter - visit.source_origin_counter) / rate
    for left_index in range(len(qualified)):
        for right_index in range(left_index + 1, len(qualified)):
            low_pair, low = qualified[left_index]
            high_pair, high = qualified[right_index]
            assert low is not None and high is not None
            if low_pair[0].fractional_tracking_cfo_hz > high_pair[0].fractional_tracking_cfo_hz:
                low_pair, high_pair, low, high = high_pair, low_pair, high, low
            separation = abs(
                circular_frequency_delta(
                    low_pair[0].fractional_tracking_cfo_hz,
                    high_pair[0].fractional_tracking_cfo_hz,
                )
            )
            if separation < 5_000:
                continue
            common = 0.5 * (low["center_sample"] + high["center_sample"])
            low_phase = (
                low["phase_rad"]
                + 2 * np.pi * low["relative_frequency_hz"] * (common - low["center_sample"]) / rate
            )
            high_phase = (
                high["phase_rad"]
                + 2
                * np.pi
                * high["relative_frequency_hz"]
                * (common - high["center_sample"])
                / rate
            )
            low_dt = (common - low["center_sample"]) / rate
            high_dt = (common - high["center_sample"]) / rate
            async_sigma = (
                2
                * np.pi
                * math.hypot(
                    low_dt * low["relative_frequency_standard_error_hz"],
                    high_dt * high["relative_frequency_standard_error_hz"],
                )
            )
            output.append(
                {
                    "low_rx0_tracking_cfo_hz": low_pair[0].fractional_tracking_cfo_hz,
                    "high_rx0_tracking_cfo_hz": high_pair[0].fractional_tracking_cfo_hz,
                    "alias_aware_signal_separation_hz": separation,
                    "receiver_offset_hz": offset,
                    "common_session_time_s": origin + common / rate,
                    "wrapped_high_minus_low_rad": float(
                        np.angle(np.exp(1j * (high_phase - low_phase)))
                    ),
                    "standard_error_rad": math.hypot(
                        math.radians(
                            math.hypot(
                                low["phase_standard_error_deg"], high["phase_standard_error_deg"]
                            )
                        ),
                        async_sigma,
                    ),
                    "asynchronous_correction_standard_error_rad": async_sigma,
                    "exact_to_control_power_ratio_floor": min(
                        low["exact_to_control_power_ratio_floor"],
                        high["exact_to_control_power_ratio_floor"],
                    ),
                    "phase_resultant_floor": min(low["resultant_length"], high["resultant_length"]),
                }
            )
    return output


def run(
    bulk_root: Path,
    session_id: str,
    visits: tuple[int, ...],
    *,
    delay_search_visits: frozenset[int],
    subband_visits: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    if not 1 <= len(visits) <= 20 or len(set(visits)) != len(visits):
        raise ValueError("select between one and twenty unique visits")
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows = []
    try:
        inspected = store.inspect(session_id)
        with AdaptiveHopAnalysisInputStore(store).source(session_id) as source:
            configuration = AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,
                probe_stride_ms=10,
            )
            for index in visits:
                iq = source.read_visit(index)
                midpoint = len(iq) // 2
                train = cross_ambiguity_peak(
                    iq[:midpoint],
                    configuration.sample_rate_hz,
                    maximum_delay_samples=12 if index in delay_search_visits else 0,
                )
                hold_peak = cross_ambiguity_peak(
                    iq[midpoint:],
                    configuration.sample_rate_hz,
                    maximum_delay_samples=12 if index in delay_search_visits else 0,
                )
                hold = iq[midpoint:]
                controls = {
                    "trained_frequency_held_coherence": coherence_at(
                        hold, configuration.sample_rate_hz, train.frequency_hz, train.delay_samples
                    ),
                    "half_symbol_alias_held_coherence": coherence_at(
                        hold,
                        configuration.sample_rate_hz,
                        train.frequency_hz + SYMBOL_ALIAS_HZ / 2,
                        train.delay_samples,
                    ),
                    "minus_half_symbol_alias_held_coherence": coherence_at(
                        hold,
                        configuration.sample_rate_hz,
                        train.frequency_hz - SYMBOL_ALIAS_HZ / 2,
                        train.delay_samples,
                    ),
                    "plus_symbol_alias_held_coherence": coherence_at(
                        hold,
                        configuration.sample_rate_hz,
                        train.frequency_hz + SYMBOL_ALIAS_HZ,
                        train.delay_samples,
                    ),
                    "minus_symbol_alias_held_coherence": coherence_at(
                        hold,
                        configuration.sample_rate_hz,
                        train.frequency_hz - SYMBOL_ALIAS_HZ,
                        train.delay_samples,
                    ),
                    "plus_frame_alias_held_coherence": coherence_at(
                        hold,
                        configuration.sample_rate_hz,
                        train.frequency_hz + FRAME_RATE_HZ,
                        train.delay_samples,
                    ),
                    "minus_frame_alias_held_coherence": coherence_at(
                        hold,
                        configuration.sample_rate_hz,
                        train.frequency_hz - FRAME_RATE_HZ,
                        train.delay_samples,
                    ),
                    "wrong_time_held_coherence": coherence_at(
                        np.column_stack((hold[:, 0], np.roll(hold[:, 1], 5000))),
                        configuration.sample_rate_hz,
                        train.frequency_hz,
                        train.delay_samples,
                    ),
                }
                train_phasor = coherence_phasor_at(
                    iq[:midpoint],
                    configuration.sample_rate_hz,
                    train.frequency_hz,
                    train.delay_samples,
                )
                held_phasor = coherence_phasor_at(
                    hold,
                    configuration.sample_rate_hz,
                    train.frequency_hz,
                    train.delay_samples,
                ) * np.exp(
                    -2j * np.pi * train.frequency_hz * midpoint / configuration.sample_rate_hz
                )
                controls["broadband_train_held_phase_error_deg"] = _phase_error_deg(
                    float(np.angle(held_phasor)), float(np.angle(train_phasor))
                )
                analysis = analyze_adaptive_hop_visit(source, index, configuration=configuration)
                pairs = _phase_blind_pairs(analysis)
                corrected = (
                    [_correct_pair(iq, analysis, pair, train.frequency_hz) for pair in pairs]
                    if train.delay_samples == 0
                    else [None] * len(pairs)
                )
                waveform_subbands = (
                    _subband_evidence(iq, configuration.sample_rate_hz, train.frequency_hz, pairs)
                    if index in subband_visits and train.delay_samples == 0
                    else []
                )
                nuisance = None
                nuisance_corrected_pairs: list[dict[str, Any] | None] = []
                nuisance_corrected_subbands: list[dict[str, Any]] = []
                overlap_evidence = None
                if index in subband_visits and train.delay_samples == 0 and pairs:
                    nuisance_iq, nuisance = remove_common_phase_nuisance(
                        iq,
                        configuration.sample_rate_hz,
                        train.frequency_hz,
                        tuple(pair[0].fractional_tracking_cfo_hz for pair in pairs),
                    )
                    nuisance_corrected_pairs = [
                        _correct_pair(nuisance_iq, analysis, pair, train.frequency_hz)
                        for pair in pairs
                    ]
                    nuisance_corrected_subbands = _subband_evidence(
                        nuisance_iq,
                        configuration.sample_rate_hz,
                        train.frequency_hz,
                        pairs,
                    )
                    if len(pairs) == 2:
                        overlap_evidence = source_overlap_evidence(
                            nuisance_iq,
                            configuration.sample_rate_hz,
                            train.frequency_hz,
                            tuple(pair[0].fractional_tracking_cfo_hz for pair in pairs),
                        )
                rows.append(
                    {
                        "visit_index": index,
                        "target_index": analysis.target_index,
                        "train_peak": asdict(train),
                        "held_peak": asdict(hold_peak),
                        "train_held_frequency_difference_hz": hold_peak.frequency_hz
                        - train.frequency_hz,
                        "phase_recorrelation_state": (
                            "evaluated"
                            if train.delay_samples == 0
                            else "unavailable_nonzero_broadband_delay_not_applied"
                        ),
                        "controls": controls,
                        "phase_blind_pair_count": len(pairs),
                        "corrected_pairs": [row for row in corrected if row is not None],
                        **({"waveform_subbands": waveform_subbands} if waveform_subbands else {}),
                        **(
                            {
                                "common_phase_nuisance": nuisance,
                                "nuisance_corrected_pairs": [
                                    row for row in nuisance_corrected_pairs if row is not None
                                ],
                                "nuisance_corrected_waveform_subbands": (
                                    nuisance_corrected_subbands
                                ),
                                **(
                                    {"source_overlap_evidence": overlap_evidence}
                                    if overlap_evidence is not None
                                    else {}
                                ),
                            }
                            if nuisance is not None
                            else {}
                        ),
                        "double_differences": _double_differences(
                            analysis, pairs, corrected, train.frequency_hz
                        ),
                    }
                )
        body = {
            "schema_version": 1,
            "kind": "adaptive_dual_rx_raw_cross_ambiguity_phase_research",
            "session_id": session_id,
            "input_manifest_sha256": inspected.manifest_sha256,
            "probe_stride_ms": 10,
            "selected_visit_indexes": list(visits),
            "frequency_authority": "first_60ms_broadband_rx1_times_conjugate_rx0",
            "validation": "held_second_60ms_and_wrong_frequency_time_controls",
            "published_phase_v2_modified": False,
            "visits": rows,
        }
        body["evidence_sha256"] = sha256_digest(canonical_json_bytes(body))
        return body
    finally:
        store.close()


def render(document: dict[str, Any], path: Path) -> None:
    visits = document["visits"]
    figure, axes = plt.subplots(3, 1, figsize=(11, 10), layout="constrained")
    indexes = np.asarray([row["visit_index"] for row in visits])
    train = np.asarray([row["train_peak"]["frequency_hz"] for row in visits]) / 1000
    held = np.asarray([row["held_peak"]["frequency_hz"] for row in visits]) / 1000
    axes[0].plot(indexes, train, "o-", label="first 60 ms authority")
    axes[0].plot(indexes, held, "x--", label="held second 60 ms peak")
    axes[0].set_ylabel("RX1−RX0 frequency (kHz)")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    labels = (
        "trained",
        "+half symbol",
        "−half symbol",
        "+symbol",
        "−symbol",
        "+750 Hz",
        "−750 Hz",
        "wrong time",
    )
    keys = (
        "trained_frequency_held_coherence",
        "half_symbol_alias_held_coherence",
        "minus_half_symbol_alias_held_coherence",
        "plus_symbol_alias_held_coherence",
        "minus_symbol_alias_held_coherence",
        "plus_frame_alias_held_coherence",
        "minus_frame_alias_held_coherence",
        "wrong_time_held_coherence",
    )
    values = [np.median([row["controls"][key] for row in visits]) for key in keys]
    axes[1].bar(labels, values)
    axes[1].set_ylabel("median held coherence")
    axes[1].tick_params(axis="x", rotation=20)
    nuisance_rows = [row for row in visits if "nuisance_corrected_waveform_subbands" in row]
    if nuisance_rows:

        def difference(row: dict[str, Any], key: str, half: str) -> float:
            subbands = row[key]
            value = subbands[1][half]["phase_deg"] - subbands[0][half]["phase_deg"]
            return math.degrees(float(np.angle(np.exp(1j * math.radians(value)))))

        nuisance_indexes = [row["visit_index"] for row in nuisance_rows]
        for key, half, label, marker in (
            ("waveform_subbands", "first_60ms", "raw first 60 ms", "o"),
            ("waveform_subbands", "held_second_60ms", "raw held 60 ms", "x"),
            (
                "nuisance_corrected_waveform_subbands",
                "first_60ms",
                "nuisance-corrected first 60 ms",
                "s",
            ),
            (
                "nuisance_corrected_waveform_subbands",
                "held_second_60ms",
                "nuisance-corrected held 60 ms",
                "+",
            ),
        ):
            axes[2].plot(
                nuisance_indexes,
                [difference(row, key, half) for row in nuisance_rows],
                marker=marker,
                label=label,
            )
        axes[2].set_xlabel("visit index")
        axes[2].legend(ncol=2, fontsize=8)
        axes[2].set_ylabel("waveform high−low phase (deg)\nwrapped 360°")
    else:
        points = [
            (
                row["visit_index"],
                hypothesis["common_session_time_s"],
                math.degrees(hypothesis["wrapped_high_minus_low_rad"]),
                math.degrees(hypothesis["standard_error_rad"]),
            )
            for row in visits
            for hypothesis in row["double_differences"]
        ]
        if points:
            times = np.asarray([row[1] for row in points])
            axes[2].errorbar(
                times, [row[2] for row in points], yerr=[row[3] for row in points], fmt="o"
            )
        axes[2].set_xlabel("session time (s)")
        axes[2].set_ylabel("corrected high−low phase (deg)\nwrapped 360°")
    axes[2].grid(alpha=0.25)
    figure.suptitle(f"{document['session_id']} raw-IQ branch validation (research V1)")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--visits", default=",".join(map(str, DEFAULT_VISITS)))
    parser.add_argument("--delay-search-visits", default="1065,1109,1136")
    parser.add_argument("--subband-visits", default="")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = run(
        args.bulk_root,
        args.session_id,
        tuple(int(value) for value in args.visits.split(",") if value),
        delay_search_visits=frozenset(
            int(value) for value in args.delay_search_visits.split(",") if value
        ),
        subband_visits=frozenset(int(value) for value in args.subband_visits.split(",") if value),
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render(document, args.png)
    print(
        json.dumps(
            {
                "json": str(args.json),
                "png": str(args.png),
                "visits": len(document["visits"]),
                "evidence_sha256": document["evidence_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
