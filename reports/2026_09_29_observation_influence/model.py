import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_09_29_unassociated_trend"))
from trend_mixture import contrast_density, trend_density  # noqa: E402


def terms(y, times, prediction, derivative):
    """Full mixture gradient and observation cross derivative, visible candidates only."""
    y = np.asarray(y)
    n = len(y)
    residual = y[None] - prediction
    log_density, influence = contrast_density(residual)
    signal = log_density + math.log(0.8) - math.log(len(prediction))
    background = trend_density(y, times) + math.log(0.2)
    normal = np.logaddexp(np.logaddexp.reduce(signal), background)
    probabilities = np.exp(signal - normal)
    bg_probability = np.exp(background - normal)
    centered = residual - residual[:, :1]
    centered -= centered.mean(axis=1, keepdims=True)
    denominator = 4 * 100**2 + np.sum(centered**2, axis=1)
    alpha = (n + 3) / denominator
    component_gradient = np.einsum("kn,kna->ka", influence, derivative)
    centered_d = derivative - derivative.mean(axis=1, keepdims=True)
    component_cross = alpha[:, None, None] * centered_d
    component_cross -= (
        2 * centered[:, :, None] * component_gradient[:, None, :] / denominator[:, None, None]
    )
    z = y - y[0]
    z -= z.mean()
    t = np.asarray(times) - np.mean(times)
    t2 = t @ t
    if t2:
        direction = t / np.sqrt(t2)
        projected = (z @ direction) * direction
        inverse_z = (z - projected) / 100**2 + projected / (100**2 + 2000**2 * t2)
    else:
        inverse_z = z / 100**2
    bg_y_gradient = -(n + 3) / (4 + z @ inverse_z) * inverse_z
    mixture_y_gradient = -probabilities @ influence + bg_probability * bg_y_gradient
    cross = np.einsum("k,kna->an", probabilities, component_cross)
    cross += np.einsum(
        "k,ka,kn->an", probabilities, component_gradient, -influence - mixture_y_gradient
    )
    return float(normal), probabilities @ component_gradient, cross
