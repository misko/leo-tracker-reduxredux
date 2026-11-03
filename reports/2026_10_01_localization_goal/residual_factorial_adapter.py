"""Independent residual-family and scale controls over fixed associations."""
from dataclasses import replace

import numpy as np
from nonlinear_gaussian_adapter import FixedGaussianPort

from leo.analysis.robust_likelihood import student_t_logpdf


class FixedResidualPort(FixedGaussianPort):
    def __init__(self, base, assignment, *, family, scale):
        super().__init__(base, assignment)
        if family not in ('gaussian', 'student') or not np.isfinite(scale) or scale <= 0:
            raise ValueError('invalid residual family or scale')
        self.family, self.scale = family, scale

    def predict_selected(self, state, index):
        prediction = super().predict_selected(state, index)
        return replace(prediction, covariance=prediction.covariance*(self.scale/2))

    def score_selected(self, state, index):
        if self.family == 'gaussian' or index != self.assignment or index == self.candidate_count:
            return super().score_selected(state, index)
        prediction = self.predict_selected(state, index)
        if not prediction.eligible:
            return -np.inf
        return float(np.log(self.base.config.signal_prior/self.candidate_count)
                     +student_t_logpdf(self.observation-prediction.mean,
                                      prediction.covariance, 4.))
