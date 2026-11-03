"""A normalized smooth-curve alternative to an identified satellite track.

The background uses raw radio values and times, never a satellite or position.
Degree is marginalized with fixed prior masses and Gaussian coefficient priors.
"""

import numpy as np
from dsx01_joint_marginal import integrated_gaussian

from leo.analysis.research.retained_track_likelihood import PERIOD


def background_logprob(values, times, noise):
    y, t = np.asarray(values, float), np.asarray(times, float)
    if y.ndim != 1 or t.shape != y.shape or len(y) < 6 or not np.isfinite(t).all():
        raise ValueError("at least six matching finite smooth-curve times required")
    span = float(np.ptp(t))
    if span <= 0:
        raise ValueError("nonzero time support required")
    sigma = np.broadcast_to(np.asarray(noise, float), y.shape)
    z = 2 * (t - (t.min() + t.max()) / 2) / span
    basis = np.polynomial.legendre.legvander(z, 4)
    scale = np.array([PERIOD / np.sqrt(12), 3000 * span / 2, 30000, 15000, 7500])
    full = basis * scale
    normalizer = len(y) * np.log(2 * np.pi) + 2 * np.log(sigma).sum()
    scores = []
    for degree in range(1, 5):
        result = integrated_gaussian(y, full[:, : degree + 1], sigma)
        scores.append(float(result["residual"] @ result["residual"] + normalizer))
    masses = np.array([0.4, 0.3, 0.2, 0.1])
    joint = np.log(masses) - np.array(scores) / 2
    probability = np.logaddexp.reduce(joint)
    return dict(
        log_probability=float(probability),
        degree_costs=scores,
        degree_posterior=np.exp(joint - probability),
    )
