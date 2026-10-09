"""Normalized soft-detectability likelihood algebra; synthetic research only."""

import numpy as np

from leo.analysis.regional_position_score import ALIAS_HZ, circular


def likelihood(measured, prediction, visibility, score):
    measured, prediction, visibility = (
        np.asarray(x, float) for x in (measured, prediction, visibility)
    )
    if (
        prediction.ndim != 2
        or visibility.shape != prediction.shape
        or measured.shape != (len(prediction),)
    ):
        raise ValueError("matching observation/satellite arrays required")
    if (
        not all(np.isfinite(x).all() for x in (measured, prediction, visibility))
        or np.any(visibility < 0)
        or np.any(visibility > 1)
    ):
        raise ValueError("finite visibility in[0,1] required")
    count = prediction.shape[1]
    if count <= score.detection_budget or not 0 < score.sigma_hz <= 1000 or score.clutter_rate <= 0:
        raise ValueError("positive narrow Gaussian/clutter and valid detection budget required")
    q = score.detection_budget / count
    p = q * visibility
    residual = circular(measured[:, None] - prediction)
    gaussian = np.exp(-0.5 * (residual / score.sigma_hz) ** 2) / (
        score.sigma_hz * np.sqrt(2 * np.pi)
    )
    signal = p / (1 - p) * gaussian
    total = score.clutter_rate / ALIAS_HZ + signal.sum(axis=1)
    log_p0 = -score.clutter_rate + np.log1p(-p).sum(axis=1)
    nll = np.sum(-log_p0 + np.log(-np.expm1(log_p0)) - np.log(total))
    responsibility = signal / total[:, None]
    dv = q / ((1 - p) * (-np.expm1(log_p0))[:, None]) - q * gaussian / (
        (1 - p) ** 2 * total[:, None]
    )
    return dict(
        nll=float(nll),
        responsibilities=responsibility,
        prediction_gradient=-responsibility * residual / score.sigma_hz**2,
        visibility_gradient=dv,
    )
