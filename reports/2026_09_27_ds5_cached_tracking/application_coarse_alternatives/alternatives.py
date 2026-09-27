"""Research-only rounded-template alternatives for the folded-anchor grid."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from leo.analysis.starlink import acquisition
from leo.analysis.starlink.templates import FRAME_RATE_HZ, OFDM_SYMBOL_DURATION_S


def _geometry(values, sample_rate_hz, symbols):
    starts = np.fromiter(
        (round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S) for symbol in symbols),
        dtype=np.intp,
    )
    stops = np.fromiter(
        (round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S) for symbol in symbols),
        dtype=np.intp,
    )
    offsets = []
    frame = 0
    while (offset := round(frame * sample_rate_hz / FRAME_RATE_HZ)) < len(values):
        offsets.append(offset)
        frame += 1
    return starts, stops, np.asarray(offsets, dtype=np.intp)


def _rotated_references(reference, frequencies, sample_rate_hz):
    indexes = np.arange(len(reference), dtype=float)
    rotation = np.exp(
        2j * np.pi * indexes[:, None] * np.asarray(frequencies)[None, :] / sample_rate_hz
    )
    return reference[:, None] * rotation


def _fold(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    frequencies: tuple[float, ...],
    symbols: tuple[int, ...],
    epoch_count: int,
    correlations: Callable[[np.ndarray, np.ndarray], np.ndarray],
) -> tuple[np.ndarray, ...]:
    samples = np.asarray(values, dtype=np.complex128)
    reference = np.asarray(template, dtype=np.complex128)
    starts, stops, offsets = _geometry(samples, sample_rate_hz, symbols)
    prefix = acquisition._power_prefix(samples)
    accumulated = np.zeros((epoch_count, len(frequencies)), dtype=float)
    support = np.zeros(epoch_count, dtype=np.int32)
    for local_start, local_stop in zip(starts, stops, strict=True):
        selected = reference[local_start:local_stop]
        reference_energy = 0.0
        for value in selected:
            reference_energy += value.real * value.real + value.imag * value.imag
        rotated = _rotated_references(selected, frequencies, sample_rate_hz)
        all_correlations = correlations(samples, rotated)
        valid_position_count = len(samples) - len(selected) + 1
        for frame_offset in offsets:
            base = int(local_start + frame_offset)
            if base >= valid_position_count:
                break
            valid_epochs = min(valid_position_count - base, epoch_count)
            positions = base + np.arange(valid_epochs)
            received_energy = prefix[positions + len(selected)] - prefix[positions]
            received_energy = np.maximum(received_energy, 0.0)
            denominator = np.sqrt(reference_energy * received_energy)
            chosen = all_correlations[positions]
            magnitude = np.sqrt(chosen.real * chosen.real + chosen.imag * chosen.imag)
            np.divide(
                magnitude,
                denominator[:, None],
                out=magnitude,
                where=denominator[:, None] > 0,
            )
            magnitude[denominator <= 0] = 0.0
            accumulated[:valid_epochs] += magnitude
            support[:valid_epochs] += 1
    scores = np.divide(
        accumulated,
        support[:, None],
        out=np.zeros_like(accumulated),
        where=support[:, None] > 0,
    )
    return tuple(scores[:, frequency].copy() for frequency in range(len(frequencies)))


def _numpy_correlations(samples: np.ndarray, rotated: np.ndarray) -> np.ndarray:
    return np.stack(
        [np.correlate(samples, rotated[:, frequency], mode="valid")
         for frequency in range(rotated.shape[1])],
        axis=1,
    )


def numpy_correlate_grid(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
    epoch_count: int,
) -> tuple[np.ndarray, ...]:
    return _fold(
        values, template, sample_rate_hz, absolute_cfo_hz, symbols, epoch_count,
        _numpy_correlations,
    )


def numpy_fft_grid(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
    epoch_count: int,
) -> tuple[np.ndarray, ...]:
    sample_ffts: dict[tuple[int, int], np.ndarray] = {}

    def correlations(samples: np.ndarray, rotated: np.ndarray) -> np.ndarray:
        count = len(samples) + len(rotated) - 1
        transform_size = 1 << (count - 1).bit_length()
        key = (len(samples), transform_size)
        sample_fft = sample_ffts.get(key)
        if sample_fft is None:
            sample_fft = np.fft.fft(samples, n=transform_size)
            sample_ffts[key] = sample_fft
        kernels = np.conj(rotated[::-1].T)
        kernel_fft = np.fft.fft(kernels, n=transform_size, axis=1)
        convolved = np.fft.ifft(kernel_fft * sample_fft[None, :], axis=1)
        start = len(rotated) - 1
        stop = start + len(samples) - len(rotated) + 1
        return convolved[:, start:stop].T.copy()

    return _fold(
        values, template, sample_rate_hz, absolute_cfo_hz, symbols, epoch_count,
        correlations,
    )


def grid_delta(expected, actual) -> dict:
    left = np.stack(expected)
    right = np.stack(actual)
    peak_match = tuple(np.argmax(row) for row in left) == tuple(np.argmax(row) for row in right)
    return {
        "shape_match": left.shape == right.shape,
        "maximum_absolute_error": float(np.max(np.abs(left - right), initial=0.0)),
        "peak_indexes_exact": peak_match,
        "finite": bool(np.all(np.isfinite(right))),
    }
