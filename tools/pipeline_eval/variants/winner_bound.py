"""Real-arithmetic upper bounds for the original fractional GLRT margin."""

import numpy as np

from .refine_bank import GLRT_SIZE, LANCZOS, RATE, TAPS

GATE = 0.025
# Engineering allowance checked against the installed double-precision scorer.
ROUNDING_ALLOWANCE = 1e-8
CONTROL_BINS = (0, 1, 2, 4, 8, 16, 32, 64, -1, -2, -4, -8, -16, -32, -64)


def ceiling(correlations):
    """Square of the triangle-inequality coherent amplitude."""
    return float(np.sum(np.sum(np.abs(correlations), axis=1) ** 2))


def margin_bounds(exact_score, control):
    """Bound the final margin after computing the original exact fractional score."""
    denominator = ceiling(control)
    if denominator == 0:
        return exact_score, exact_score, exact_score
    mean = float(np.sum(np.abs(control) ** 2)) / denominator
    phases = np.exp(
        -2j * np.pi * np.asarray(CONTROL_BINS)[:, None] * np.arange(control.shape[1]) / GLRT_SIZE
    )
    sampled = float(np.max(np.sum(np.abs(control @ phases.T) ** 2, axis=0))) / denominator
    return exact_score, exact_score - mean, exact_score - max(mean, sampled)


def perturbation(template, offset, acquired_hz):
    """Coefficient change from the nearest integer to a Lanczos-shifted aperture."""
    nearest = round(offset)
    base = int(np.floor(offset))
    displacements = base - nearest + LANCZOS
    distance = offset - base - LANCZOS
    weights = np.sinc(distance) * np.sinc(distance / 8)
    weights /= weights.sum()
    weights = weights * np.exp(2j * np.pi * acquired_hz * (displacements + nearest - offset) / RATE)
    first = int(min(0, displacements[0]))
    stop = int(max(0, displacements[-1])) + TAPS
    delta = np.zeros((len(template), stop - first), dtype=np.complex128)
    conjugate = template.conj()
    for d, weight in zip(displacements, weights, strict=True):
        index = int(d) - first
        delta[:, index : index + TAPS] += weight * conjugate
    delta[:, -first : -first + TAPS] -= conjugate
    return first, stop, np.linalg.norm(delta, axis=1)


def integer_envelope(integer, integer_score, coefficient_delta, source_norm):
    """Enclose the fractional score from the original nearest-grid amplitude and norms."""
    if integer.shape != source_norm.shape:
        raise ValueError("fractional and integer bounds require the same frame/symbol support")
    magnitude = np.abs(integer)
    error = source_norm * coefficient_delta
    combined_error = np.linalg.norm(np.sum(error, axis=1))
    integer_amplitude = np.sqrt(max(0.0, integer_score) * ceiling(integer))
    denominator = np.linalg.norm(np.sum(np.maximum(magnitude - error, 0.0), axis=1))
    if denominator == 0:
        return 1.0
    return float(min(1.0, ((integer_amplitude + combined_error) / denominator) ** 2))


def can_skip(bound, incumbent):
    """Preserve gate existence and the winner. Retain possible ties."""
    return incumbent is not None and incumbent >= GATE and bound + ROUNDING_ALLOWANCE < incumbent
