"""Independent label priors with same-label correlated narrow emissions.

Research kernel only. Nearest wrapped images use B7's narrow regime; at the
alias seam omitted correlated images are far below its positive clutter floor.
Visibility is fixed while differentiating. Correlation is not label persistence.
"""

import numpy as np

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ, WindowLikelihood


def exclusive(values):
    """Positive exclusive sums; never total-minus-diagonal cancellation."""
    zeros = np.zeros(values.shape[:-1] + (1,))
    left = np.concatenate((zeros, np.cumsum(values[..., :-1], axis=-1)), axis=-1)
    right = np.concatenate((np.cumsum(values[..., :0:-1], axis=-1)[..., ::-1], zeros), axis=-1)
    return left + right


def omitted_image_log_bound(score, rho):
    """Conservative omitted toroidal Gaussian density bound (log Hz^-2).

    For |rho|<=.25 and125Hz, any non-nearest image has one coordinate
    >=L/2. Covariance's largest eigenvalue is sigma²(1+rho). Bounding
    the lattice Gaussian tail by16 times its first term is conservative
    in this narrow regime, including exact seams and all visibility masks.
    """
    return (
        np.log(16)
        - ALIAS_HZ**2 / (8 * score.sigma_hz**2 * (1 + rho))
        - np.log(2 * np.pi * score.sigma_hz**2 * np.sqrt(1 - rho**2))
    )


def paired_likelihood(measured, prediction, visible, score, pairs, rho=0.25):
    if not np.isfinite(rho) or not 0 <= rho <= 0.25:
        raise ValueError("Research correlation must be in [0, .25]")
    if score.sigma_hz != 125 or not np.isfinite(score.clutter_rate) or score.clutter_rate <= 0:
        raise ValueError("Positive clutter and fixed125Hz narrow likelihood required")
    base = likelihood(measured, prediction, visible, score)
    n, k = base.residual_hz.shape
    pair_array = np.asarray(pairs)
    if pair_array.size == 0:
        pair_array = np.empty((0, 2), dtype=int)
    if pair_array.ndim != 2 or pair_array.shape[1] != 2 or pair_array.dtype.kind not in "iu":
        raise ValueError("Integer pair indices required")
    if (
        np.any(pair_array < 0)
        or np.any(pair_array >= n)
        or len(np.unique(pair_array)) != pair_array.size
    ):
        raise ValueError("Pairs must be valid and disjoint")
    if rho == 0 or not len(pair_array):
        return base
    sigma = score.sigma_hz
    q = score.detection_budget / k
    a = q / (1 - q)
    u = score.clutter_rate / ALIAS_HZ
    if (
        u <= 0
        or omitted_image_log_bound(score, rho) + np.log(k) + 2 * np.log(a) - 2 * np.log(u) > -700
    ):
        raise ValueError("Narrow wrapped-image/clutter bound unsupported")
    residual = base.residual_hz
    signals = (
        a
        * np.asarray(visible)
        * np.exp(-0.5 * (residual / sigma) ** 2)
        / (sigma * np.sqrt(2 * np.pi))
    )
    total = u + signals.sum(axis=1)
    responsibilities = base.responsibilities.copy()
    clutter = base.clutter_probability.copy()
    gradient = base.prediction_gradient.copy()
    nll = base.nll
    variance = sigma**2 * (1 - rho**2)
    for start in range(0, len(pair_array), 256):
        i, j = pair_array[start : start + 256].T
        ri, rj = residual[i], residual[j]
        # A sum of positive squares avoids cancellation in the Gaussian exponent.
        exponent = ((ri - rho * rj) ** 2 + (1 - rho**2) * rj**2) / (2 * variance)
        # Scale by singleton totals before multiplying, so tiny clutter squared
        # never underflows. This density is the pair/independent density ratio.
        si, sj = signals[i] / total[i, None], signals[j] / total[j, None]
        ui, uj = u / total[i], u / total[j]
        both_visible = np.asarray(visible[i]) & np.asarray(visible[j])
        diagonal = np.zeros_like(ri)
        log_diagonal = (
            2 * np.log(a)
            - exponent
            - np.log(2 * np.pi * sigma**2 * np.sqrt(1 - rho**2))
            - np.log(total[i, None])
            - np.log(total[j, None])
        )
        diagonal[both_visible] = np.exp(log_diagonal[both_visible])
        off_i = si * (uj[:, None] + exclusive(sj))
        off_j = sj * (ui[:, None] + exclusive(si))
        density = ui + off_i.sum(axis=1) + diagonal.sum(axis=1)
        if not np.isfinite(density).all() or np.any(density <= 0):
            raise ValueError("Nonfinite or nonpositive correlated density")
        nll -= np.log(density).sum()
        responsibilities[i] = (off_i + diagonal) / density[:, None]
        responsibilities[j] = (off_j + diagonal) / density[:, None]
        clutter[i], clutter[j] = ui / density, uj / density
        gradient[i] = (
            -(off_i * ri / sigma**2 + diagonal * (ri - rho * rj) / variance) / density[:, None]
        )
        gradient[j] = (
            -(off_j * rj / sigma**2 + diagonal * (rj - rho * ri) / variance) / density[:, None]
        )
    return WindowLikelihood(float(nll), responsibilities, clutter, gradient, residual)
