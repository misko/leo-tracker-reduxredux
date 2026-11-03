"""Counterfactual frequency precision, conditional on a local Gaussian design.

These matrices describe a measurement-design experiment, not a new position
estimate. Noise precisions, geometry and nuisance priors remain fixed.
"""

import numpy as np
from ds23_position_information import marginal_position_information, ellipse_scales


def precision_sweep(before_j, before_u, before_w, extra_j, extra_u, extra_w,
                    prior_precision, sigma_factors):
    factors = np.asarray(sigma_factors, float)
    if factors.ndim != 1 or not len(factors) or not np.isfinite(factors).all() or np.any(factors <= 0):
        raise ValueError('finite positive measurement standard deviation factors required')
    before = marginal_position_information(before_j, before_u, before_w, prior_precision)
    j = np.vstack((before_j, extra_j)); u = np.vstack((before_u, extra_u))
    rows = []
    for factor in factors:
        after = marginal_position_information(j, u, np.r_[before_w, extra_w/factor**2], prior_precision)
        if np.linalg.eigvalsh(after-before).min() < -1e-7:
            raise ValueError('additional independent conditional evidence lost information')
        rows.append(dict(sigma_factor=float(factor), information=after, scales=ellipse_scales(after)))
    return dict(before_information=before, before_scales=ellipse_scales(before), rows=rows)
