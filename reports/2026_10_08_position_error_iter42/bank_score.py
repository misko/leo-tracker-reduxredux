"""Narrow Gaussian likelihood with explicit candidate weight normalization."""

import numpy as np

PERIOD = 1 / 4.4e-6


def score_bank(measured, prediction, visible, score, normalization_count=None):
    count = prediction.shape[1] if normalization_count is None else normalization_count
    if count <= score.detection_budget:
        raise ValueError("Invalid candidate normalization")
    q = score.detection_budget / count
    residual = (measured[:, None] - prediction + PERIOD / 2) % PERIOD - PERIOD / 2
    signal = np.exp(-0.5 * (residual / score.sigma_hz) ** 2) * visible
    signal *= q / (1 - q) / (score.sigma_hz * np.sqrt(2 * np.pi))
    total = score.clutter_rate / PERIOD + signal.sum(axis=1)
    log_p0 = -score.clutter_rate + visible.sum(axis=1) * np.log1p(-q)
    nll = -np.sum(log_p0 - np.log(-np.expm1(log_p0)) + np.log(total))
    weight = signal / total[:, None]
    mass = float(weight.sum())
    return dict(
        nll=float(nll),
        signal_mass=mass,
        rms_hz=float(np.sqrt(np.sum(weight * residual**2) / mass)) if mass else None,
    )
