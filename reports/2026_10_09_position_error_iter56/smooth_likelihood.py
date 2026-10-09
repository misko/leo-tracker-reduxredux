"""Research-only horizon detection taper with both likelihood derivatives."""

import numpy as np

PERIOD = 1 / 4.4e-6


def taper(elevation_deg, width_deg=1.0):
    if not np.isfinite(width_deg) or width_deg <= 0:
        raise ValueError("positive finite transition width required")
    x = np.clip(np.asarray(elevation_deg, dtype=float) / width_deg, 0, 1)
    return x * x * (3 - 2 * x), 6 * x * (1 - x) / width_deg


def evaluate(measured, prediction, elevation_deg, score, width_deg=1.0):
    measured, prediction, elevation = map(np.asarray, (measured, prediction, elevation_deg))
    if (
        prediction.ndim != 2
        or elevation.shape != prediction.shape
        or measured.shape != (len(prediction),)
        or not all(np.isfinite(v).all() for v in (measured, prediction, elevation))
    ):
        raise ValueError("invalid likelihood arrays")
    if not (
        0 < score.sigma_hz <= 1000
        and score.clutter_rate > 0
        and 0 < score.detection_budget < prediction.shape[1]
    ):
        raise ValueError("unsupported narrow-Gaussian score")
    weight, derivative = taper(elevation, width_deg)
    q0 = score.detection_budget / prediction.shape[1]
    q = q0 * weight
    residual = (measured[:, None] - prediction + PERIOD / 2) % PERIOD - PERIOD / 2
    gaussian = np.exp(-0.5 * (residual / score.sigma_hz) ** 2)
    gaussian /= score.sigma_hz * np.sqrt(2 * np.pi)
    signal = q / (1 - q) * gaussian
    total = score.clutter_rate / PERIOD + signal.sum(axis=1)
    log_p0 = -score.clutter_rate + np.log1p(-q).sum(axis=1)
    one_minus_p0 = -np.expm1(log_p0)
    nll = -np.sum(log_p0 - np.log(one_minus_p0) + np.log(total))
    responsibility = signal / total[:, None]
    prediction_gradient = -responsibility * residual / score.sigma_hz**2
    q_gradient = 1 / ((1 - q) * one_minus_p0[:, None])
    q_gradient -= gaussian / (total[:, None] * (1 - q) ** 2)
    elevation_gradient = q_gradient * q0 * derivative
    return dict(
        nll=float(nll),
        prediction_gradient=prediction_gradient,
        elevation_gradient=elevation_gradient,
        responsibility=responsibility,
    )
