"""Preserve a wide-prior radio warm start across the legacy inner constructor."""

import numpy as np


def restore_radio_initialization(problem):
    """Restore supplied RX means/contrasts without changing residuals or bounds.

    FixedFamilies clips native initial band rates to +/-1 Hz/s before the wide
    wrapper is built. That discovery bound must not replace a completed warm
    start. Projection below uses only the actual final mean/contrast bounds.
    """
    beta = np.asarray(problem.starts["beta"])
    for receiver, (low, high, _, _) in enumerate(problem.pairs):
        rates = beta[4 + 2 * receiver : 6 + 2 * receiver] / 150
        mean = rates.mean() / problem.mean_sigma
        contrast = (rates[1] - rates[0]) / (2 * problem.contrast_sigma)
        problem.initial[low] = np.clip(mean, problem.lower[low], problem.upper[low])
        problem.initial[high] = np.clip(contrast, problem.lower[high], problem.upper[high])
    return problem
