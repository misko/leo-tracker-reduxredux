"""Scale actual zero-centered Gaussian timing priors, not tie-break scores.

Both common and zero-sum individual timing standard deviations are multiplied
by scale. Timing bounds, likelihood, observations and calibration remain fixed.
Raw penalized scores across prior scales are not a common evaluation metric.
"""
import math
import numpy as np


def apply(objective,scale):
    if not math.isfinite(scale) or scale<=0:raise ValueError('prior scale must be positive and finite')
    if getattr(objective,'_timing_prior_scale_applied',False):raise ValueError('prior scaling already applied')
    base=objective.base
    original_penalty=base.penalty
    original_curvature=objective.curvature
    factor=1./scale**2
    def penalty(vector):
        value,gradient=original_penalty(vector)
        return value*factor,gradient*factor
    def curvature(vector):
        matrix=original_curvature(vector).copy()
        if base.common_prior:matrix[6,6]+=(factor-1.)/100.
        size=objective.size
        matrix[7:size,7:size]+=(factor-1.)*np.eye(size-7)
        return matrix
    base.penalty=penalty
    objective.curvature=curvature
    objective._timing_prior_scale_applied=True
    return objective
