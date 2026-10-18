"""Small numerical kernels for shared satellite corrections on whole curves."""

import numpy as np

NOISE_HZ = 150.0
BIAS_HZ = 1000.0
PERIOD_HZ = 1 / 4.4e-6


def profile_curve(observed, predicted):
    """Profile one integer native alias and one Gaussian constant per curve."""
    y, f = np.asarray(observed), np.atleast_2d(predicted)
    if y.ndim != 1 or f.shape[1] != len(y) or not np.isfinite(f).all():
        raise ValueError("matching finite curve predictions required")
    raw = y - f
    aliases = np.rint(-raw.mean(axis=1) / PERIOD_HZ)
    raw = raw + aliases[:, None] * PERIOD_HZ
    prior_count = NOISE_HZ**2 / BIAS_HZ**2
    bias = raw.sum(axis=1) / (len(y) + prior_count)
    residual = raw - bias[:, None]
    mse = np.mean(residual**2, axis=1)
    volume = NOISE_HZ**2 * np.log1p(len(y) / prior_count)
    score = (len(y) * mse + prior_count * bias**2 + volume) / len(y)
    return dict(residual=residual, aliases=aliases, bias=bias, rms=np.sqrt(mse), score=score)


def ridge_shared_fit(features, values, weights, prior_covariance, active):
    """MAP tangent update; linear curves have exactly zero calibration vote.

    Each feature block uses absolute shared coordinates. Every curve has its
    existing Gaussian constant eliminated analytically. A satellite prior is
    added once, regardless of how many curves carry the satellite.
    """
    covariance = np.asarray(prior_covariance, float)
    if covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]:
        raise ValueError("square shared prior covariance required")
    precision = np.linalg.inv(covariance) * NOISE_HZ**2
    information = np.zeros_like(covariance)
    rhs = np.zeros(len(covariance))
    count = 0
    for x, y, weight, curved in zip(features, values, weights, active, strict=True):
        if not curved or weight <= 0:
            continue
        x, y = np.asarray(x), np.asarray(y)
        if x.shape != (len(y), len(covariance)):
            raise ValueError("shared feature dimensions differ")
        w = weight * min(1.0, 50 / len(y))
        denom = len(y) + NOISE_HZ**2 / BIAS_HZ**2
        sx, sy = x.sum(axis=0), y.sum()
        information += w * (x.T @ x - np.outer(sx, sx) / denom)
        rhs += w * (x.T @ y - sx * sy / denom)
        count += len(y)
    theta = np.linalg.solve(information + precision, rhs)
    return theta, information, count


def soft_curve_responsibilities(score, rms, bias, visible, points):
    """Whole-curve signal/clutter E step, before final residual-structure gates.

    These experimental responsibilities guide curved-track proposals; they are
    not identity probabilities and never bypass the final whole-curve tests.
    """
    score, rms, bias, visible = map(np.asarray, (score, rms, bias, visible))
    n = min(points, 50)
    log_signal = (
        np.log(0.98 / score.size)
        - n * np.log(NOISE_HZ * np.sqrt(2 * np.pi))
        - 0.5 * n * score / NOISE_HZ**2
    )
    log_signal = np.where(visible & (rms <= 900) & (abs(bias) <= 5000), log_signal, -np.inf)
    clutter = np.log(0.02) - n * np.log(PERIOD_HZ)
    maximum = max(float(np.max(log_signal)), clutter)
    signal = np.exp(log_signal - maximum)
    background = np.exp(clutter - maximum)
    denominator = signal.sum() + background
    return signal / denominator, float(background / denominator)
