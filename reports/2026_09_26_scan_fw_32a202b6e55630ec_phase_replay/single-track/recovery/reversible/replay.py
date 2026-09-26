"""Reversible phasor bookkeeping for differential-phase replay.

This module deliberately makes no claim that either the cached phase or the
declared uncorrected gauge is geometric phase.  Every removal is represented
by a unit phasor and retained, so the input phasor can be reconstructed.
"""
import numpy as np

TAU = 2.0 * np.pi


def wrap_radians(value):
    return (np.asarray(value) + np.pi) % TAU - np.pi


def unit_phase(cycles):
    """Return exp(i 2 pi cycles), reducing cycles first for stable arguments."""
    fractional = np.remainder(np.asarray(cycles, dtype=float), 1.0)
    return np.exp(1j * TAU * fractional)


def reversible_derotate(observed, removed_cycles):
    """Derotate and reconstruct complex samples without discarding correction."""
    observed = np.asarray(observed, dtype=complex)
    correction = unit_phase(removed_cycles)
    residual = observed * np.conj(correction)
    reconstructed = residual * correction
    return residual, reconstructed, correction


def weighted_unit_mean(products, weights):
    products = np.asarray(products, dtype=complex)
    weights = np.asarray(weights, dtype=float)
    good = np.isfinite(products.real) & np.isfinite(products.imag) & np.isfinite(weights) & (weights > 0)
    unit = np.divide(products, np.abs(products), out=np.zeros_like(products), where=np.abs(products) > 0)
    numerator = np.sum(np.where(good, unit * weights, 0.0), axis=1)
    denominator = np.sum(np.where(good, weights, 0.0), axis=1)
    result = np.full(products.shape[0], np.nan + 1j * np.nan)
    result[denominator > 0] = numerator[denominator > 0] / denominator[denominator > 0]
    return result


def causal_previous_increment(time_s, phasor, *, gap_s=0.003):
    """Predict phase from the two preceding observations within each gap segment.

    Returned cycles are a reversible processing coordinate, not an estimate of
    hardware-only phase. No correction or integer-cycle continuation is
    produced for the first two frames after a gap.
    """
    time_s = np.asarray(time_s, dtype=float)
    phase = np.angle(np.asarray(phasor, dtype=complex))
    prediction = np.full(len(phase), np.nan)
    segment = np.full(len(phase), -1, dtype=int)
    current_segment = -1
    for index in range(len(phase)):
        if not np.isfinite(phase[index]):
            continue
        new_segment = (index == 0 or not np.isfinite(phase[index - 1])
                       or time_s[index] <= time_s[index - 1]
                       or time_s[index] - time_s[index - 1] > gap_s)
        if new_segment:
            current_segment += 1
        segment[index] = current_segment
        if index < 2 or new_segment or segment[index - 1] != segment[index - 2]:
            continue
        increment = wrap_radians(phase[index - 1] - phase[index - 2])
        prediction[index] = phase[index - 1] + increment
    return prediction / TAU, segment


def contiguous_relative_phase(time_s, phasor, *, gap_s=0.003):
    """Unwrap only inside observed contiguous segments and zero each segment."""
    time_s = np.asarray(time_s, dtype=float)
    phase = np.angle(np.asarray(phasor, dtype=complex))
    relative = np.full(len(phase), np.nan)
    segment = np.full(len(phase), -1, dtype=int)
    current_segment = -1
    for index in range(len(phase)):
        if not np.isfinite(phase[index]):
            continue
        new_segment = (index == 0 or not np.isfinite(phase[index - 1])
                       or time_s[index] <= time_s[index - 1]
                       or time_s[index] - time_s[index - 1] > gap_s)
        if new_segment:
            current_segment += 1
        segment[index] = current_segment
        relative[index] = 0.0 if new_segment else relative[index - 1] + wrap_radians(phase[index] - phase[index - 1])
    return relative, segment
