"""Move feasible frequency-curve starts between receiver positions.

This is initialization only. It preserves the reference model approximately;
the target-position likelihood and all original priors are subsequently fitted.
"""

import numpy as np


def transport_bias_phase(
    reference, target, timing, mass, phase_s, bias_hz, *, scale_hz, phase_sigma_s, bias_sigma_hz
):
    reference, target, timing, mass = (
        np.asarray(x, float) for x in (reference, target, timing, mass)
    )
    phase, bias = np.asarray(phase_s, float), np.asarray(bias_hz, float)
    if (
        reference.ndim != 2
        or any(x.shape != reference.shape for x in (target, timing, mass))
        or phase.shape != (reference.shape[1],)
        or bias.shape != phase.shape
        or any(not np.isfinite(x).all() for x in (reference, target, timing, mass, phase, bias))
        or (mass < 0).any()
        or not np.isfinite([scale_hz, phase_sigma_s, bias_sigma_hz]).all()
        or min(scale_hz, phase_sigma_s, bias_sigma_hz) <= 0
    ):
        raise ValueError("finite curve arrays, nonnegative mass and positive scales required")
    support = mass.sum(axis=0)
    denominator = np.maximum(support, 1e-30)
    difference = reference - target
    mean = (mass * difference).sum(axis=0) / denominator
    derivative = (mass * timing).sum(axis=0) / denominator
    centered = timing - derivative
    phase_step = (mass * centered * (difference - mean)).sum(axis=0) / (
        (mass * centered**2).sum(axis=0) + (scale_hz / phase_sigma_s) ** 2
    )
    moved_phase = np.clip(phase + phase_step, -10, 10)
    actual_step = moved_phase - phase
    moved_bias = np.clip(
        bias + mean - derivative * actual_step, -10 * bias_sigma_hz, 10 * bias_sigma_hz
    )
    moved_phase = np.where(support > 0, moved_phase, phase)
    moved_bias = np.where(support > 0, moved_bias, bias)
    error = target + timing * (moved_phase - phase) + moved_bias - reference - bias
    rms = np.sqrt((mass * error**2).sum(axis=0) / denominator)
    return moved_phase, moved_bias, rms
