"""Known Qin-pilot QAM metrics with inverse-noise receiver combining.

The numerical kernel is a clean, infrastructure-free port of
``leo_tracker/radio/beacon/decode.py`` at leo-tracker commit
0bb80d14759fd8496b74e7d3219a690be18565a6 and is cross-checked against
``starlink_pilot_constellation.py`` at leo-tracker-redux commit
b2b8827832715f7cd45196cd08919bcc5dd2a3f0. These metrics cover known
synchronization symbols, never user payload.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import cast

import numpy as np

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)


@dataclass(frozen=True, slots=True)
class PilotQamMetrics:
    hard_symbol_accuracy: float
    rms_evm: float
    noise_variance: float
    soft_mean_confidence: float
    soft_mean_expected_probability: float
    frame_count: int
    effective_frame_count: float


@dataclass(frozen=True, slots=True)
class PilotQamResult:
    status: NumericalStatus
    metrics: PilotQamMetrics | None
    absolute_cfo_hz: float | None
    residual_cfo_refinement_hz: float | None
    reason: str
    known_symbols_only: bool = True
    candidate_only: bool = True
    expected: np.ndarray = field(default_factory=lambda: np.empty((0, 8)), repr=False)
    equalized: np.ndarray = field(default_factory=lambda: np.empty((0, 8)), repr=False)
    frame_equalized: np.ndarray = field(default_factory=lambda: np.empty((0, 300, 8)), repr=False)


@dataclass(frozen=True, slots=True)
class CombinedPilotQamResult:
    status: NumericalStatus
    metrics: PilotQamMetrics | None
    receiver_weights: tuple[float, ...]
    reason: str
    known_symbols_only: bool = True
    candidate_only: bool = True
    equalized: np.ndarray = field(default_factory=lambda: np.empty((0, 8)), repr=False)


def analyze_pilot_qam(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    epoch_sample: int,
    absolute_cfo_hz: float,
    edge: StarlinkEdge | str = StarlinkEdge.LOWER,
) -> PilotQamResult:
    """Demodulate and cross-fit all complete known-pilot frames."""

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if epoch_sample < 0 or not math.isfinite(absolute_cfo_hz):
        raise ValueError("epoch must be nonnegative and CFO finite")
    minimum_rate_hz = 8 * 234_375.0
    if sample_rate_hz < minimum_rate_hz:
        raise ValueError(f"sample rate must be at least {minimum_rate_hz:.0f} Hz")
    starts = _complete_frame_starts(values.size, sample_rate_hz, epoch_sample)
    if not starts:
        return _empty(
            NumericalStatus.INSUFFICIENT,
            "window contains no complete known-pilot frame",
        )
    if float(np.mean(np.abs(values) ** 2)) <= np.finfo(float).tiny:
        return _empty(NumericalStatus.NO_RESULT, "window has zero signal energy")

    demodulator = _KnownPilotDemodulator(values, sample_rate_hz, selected_edge, absolute_cfo_hz)
    pilots = np.asarray([demodulator.frame(start) for start in starts], dtype=np.complex64)
    expected = qin_edge_pilot_symbols(selected_edge)
    residual_cfo_hz = _estimate_residual_cfo(pilots, expected)
    pilot_times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    reference_time_s = float(np.mean(pilot_times_s))
    pilots *= np.exp(-2j * np.pi * residual_cfo_hz * (pilot_times_s - reference_time_s))[
        None, :, None
    ]

    frame_match = np.sum(pilots * np.conj(expected)[None, :, :], axis=(1, 2))
    frame_phase = np.angle(frame_match)
    aligned = pilots * np.exp(-1j * frame_phase)[:, None, None]
    frame_energy = np.sum(np.abs(pilots) ** 2, axis=(1, 2))
    frame_quality = np.abs(frame_match) ** 2 / np.maximum(frame_energy, 1e-20)
    positive = frame_quality[frame_quality > 0]
    if positive.size:
        frame_quality = np.minimum(frame_quality, 4 * np.median(positive))
    total_quality = float(np.sum(frame_quality))
    frame_weights = (
        frame_quality / total_quality
        if total_quality > 0
        else np.full(len(starts), 1 / len(starts))
    )
    stacked = np.sum(aligned * frame_weights[:, None, None], axis=0)
    equalized = _cross_fit_equalize(stacked, expected)
    full_channel = np.mean(stacked * np.conj(expected), axis=0)
    frame_equalized = (
        aligned
        / np.where(
            np.abs(full_channel) > 1e-20,
            full_channel,
            np.complex64(1),
        )[None, None, :]
    )
    metric_values = _metric_values(equalized, expected)
    metrics = PilotQamMetrics(
        hard_symbol_accuracy=metric_values[0],
        rms_evm=metric_values[1],
        noise_variance=metric_values[2],
        soft_mean_confidence=metric_values[3],
        soft_mean_expected_probability=metric_values[4],
        frame_count=len(starts),
        effective_frame_count=float(1 / np.sum(frame_weights**2)),
    )
    return PilotQamResult(
        NumericalStatus.COMPLETE,
        metrics,
        float(absolute_cfo_hz + residual_cfo_hz),
        residual_cfo_hz,
        "known synchronization-pilot quality; payload was not decoded",
        expected=_freeze(expected),
        equalized=_freeze(equalized),
        frame_equalized=_freeze(frame_equalized),
    )


def combine_receiver_qam(receivers: tuple[PilotQamResult, ...]) -> CombinedPilotQamResult:
    """Inverse-noise combine independently equalized receiver evidence."""

    if len(receivers) < 2:
        return CombinedPilotQamResult(
            NumericalStatus.INSUFFICIENT,
            None,
            (),
            "at least two receiver results are required for combining",
        )
    if any(
        item.status is not NumericalStatus.COMPLETE or item.metrics is None for item in receivers
    ):
        return CombinedPilotQamResult(
            NumericalStatus.NO_RESULT,
            None,
            (),
            "every receiver must have complete QAM evidence",
        )
    first_shape = receivers[0].equalized.shape
    if any(item.equalized.shape != first_shape for item in receivers):
        raise ValueError("receiver equalized symbol shapes differ")
    expected = receivers[0].expected
    if any(not np.array_equal(item.expected, expected) for item in receivers[1:]):
        raise ValueError("receiver expected pilot matrices differ")
    noise = np.asarray(
        [max(cast(PilotQamMetrics, item.metrics).noise_variance, 1e-6) for item in receivers]
    )
    weights = (1 / noise) / np.sum(1 / noise)
    equalized = sum(weights[index] * item.equalized for index, item in enumerate(receivers))
    values = _metric_values(equalized, expected)
    frame_count = min(item.frame_equalized.shape[0] for item in receivers)
    metrics = PilotQamMetrics(
        hard_symbol_accuracy=values[0],
        rms_evm=values[1],
        noise_variance=values[2],
        soft_mean_confidence=values[3],
        soft_mean_expected_probability=values[4],
        frame_count=frame_count,
        effective_frame_count=float(frame_count),
    )
    return CombinedPilotQamResult(
        NumericalStatus.COMPLETE,
        metrics,
        tuple(float(value) for value in weights),
        "inverse-noise combination of independently equalized known pilots",
        equalized=_freeze(equalized),
    )


class _KnownPilotDemodulator:
    def __init__(
        self,
        samples: np.ndarray,
        sample_rate_hz: float,
        edge: StarlinkEdge,
        absolute_cfo_hz: float,
    ) -> None:
        self._samples = samples
        self._rate = sample_rate_hz
        self._cfo = absolute_cfo_hz
        self._frequencies = edge_frequencies_hz(edge)
        self._solves: dict[tuple[int, int], np.ndarray] = {}

    def frame(self, frame_start: int) -> np.ndarray:
        result = np.empty((300, 8), dtype=np.complex128)
        for row, symbol in enumerate(range(2, 302)):
            local_start = round(symbol * self._rate * OFDM_SYMBOL_DURATION_S)
            local_stop = round((symbol + 1) * self._rate * OFDM_SYMBOL_DURATION_S)
            key = (local_start, local_stop)
            solve = self._solves.get(key)
            if solve is None:
                local = np.arange(local_start, local_stop)
                time_s = (
                    local / self._rate - symbol * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S
                )
                design = np.exp(
                    2j * np.pi * time_s[:, None] * self._frequencies[None, :]
                ) / math.sqrt(8)
                solve = np.linalg.pinv(design)
                self._solves[key] = solve
            start, stop = frame_start + local_start, frame_start + local_stop
            values = np.asarray(self._samples[start:stop], dtype=np.complex128).copy()
            values *= np.exp(-2j * np.pi * self._cfo * np.arange(start, stop) / self._rate)
            result[row] = solve @ values
        return result


def _estimate_residual_cfo(pilots: np.ndarray, expected: np.ndarray) -> float:
    frame_match = np.sum(pilots * np.conj(expected)[None, :, :], axis=(1, 2))
    aligned = pilots * np.exp(-1j * np.angle(frame_match))[:, None, None]
    channel = np.mean(aligned * np.conj(expected)[None, :, :], axis=(0, 1))
    symbol_match = np.sum(
        pilots * np.conj(expected)[None, :, :] * np.conj(channel)[None, None, :],
        axis=2,
    )
    phase = np.unwrap(np.angle(symbol_match), axis=1)
    time_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    time_s -= np.mean(time_s)
    slopes = []
    for frame in range(pilots.shape[0]):
        weight = np.abs(symbol_match[frame])
        usable = weight > np.median(weight) * 0.25
        if np.count_nonzero(usable) >= 20:
            slopes.append(
                np.polyfit(
                    time_s[usable],
                    phase[frame, usable],
                    1,
                    w=np.sqrt(weight[usable]),
                )[0]
                / (2 * np.pi)
            )
    return float(np.clip(np.median(slopes) if slopes else 0.0, -2_000, 2_000))


def _cross_fit_equalize(stacked: np.ndarray, expected: np.ndarray) -> np.ndarray:
    equalized = np.empty_like(stacked)
    indexes = np.arange(300)
    for parity in range(2):
        training = indexes % 2 != parity
        testing = ~training
        channel = np.mean(stacked[training] * np.conj(expected[training]), axis=0)
        equalized[testing] = stacked[testing] / np.where(
            np.abs(channel) > 1e-20,
            channel,
            np.complex64(1),
        )
    return equalized


def _metric_values(
    equalized: np.ndarray, expected: np.ndarray
) -> tuple[float, float, float, float, float]:
    expected_values = np.broadcast_to(expected, equalized.shape)
    states = _constellation_states(expected)
    constellation = np.exp(0.5j * np.pi * (np.arange(4, dtype=float) + 0.5))
    distance = np.abs(equalized[..., None] - constellation) ** 2
    hard = np.argmin(distance, axis=-1)
    error = equalized - expected_values
    noise_variance = max(float(np.mean(np.abs(error) ** 2)), 1e-6)
    logits = -distance / noise_variance
    logits -= np.max(logits, axis=-1, keepdims=True)
    likelihood = np.exp(logits)
    probabilities = likelihood / np.sum(likelihood, axis=-1, keepdims=True)
    known = np.broadcast_to(states, hard.shape)
    expected_probability = np.take_along_axis(probabilities, known[..., None], axis=-1)[..., 0]
    return (
        float(np.mean(hard == known)),
        float(np.sqrt(np.mean(np.abs(error) ** 2))),
        noise_variance,
        float(np.mean(np.max(probabilities, axis=-1))),
        float(np.mean(expected_probability)),
    )


def _constellation_states(values: np.ndarray) -> np.ndarray:
    phases = np.angle(values) / (np.pi / 2) - 0.5
    return np.mod(np.rint(phases).astype(int), 4)


def _complete_frame_starts(
    sample_count: int, sample_rate_hz: float, epoch_sample: int
) -> tuple[int, ...]:
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    result: list[int] = []
    frame = 0
    while True:
        start = epoch_sample + round(frame * sample_rate_hz / FRAME_RATE_HZ)
        if start + frame_content > sample_count:
            return tuple(result)
        result.append(start)
        frame += 1


def _empty(status: NumericalStatus, reason: str) -> PilotQamResult:
    return PilotQamResult(status, None, None, None, reason)


def _freeze(values: np.ndarray) -> np.ndarray:
    output = np.asarray(values).copy()
    output.flags.writeable = False
    return output
