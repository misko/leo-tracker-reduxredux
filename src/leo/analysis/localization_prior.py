"""Student-t scalar nuisance-prior factors for the localization solver.

These factors are model constraints, not additional radio observations. Callers
must record their identifiers separately and remove the matching Gaussian prior.
"""
from __future__ import annotations

import numpy as np

from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.robust_likelihood import student_t_logpdf


class ScalarStudentPriorPort:
    """A normalized zero-mean t4 prior with an explicitly specified variance."""

    candidate_count = 1
    priors_piecewise_constant = True

    def __init__(self, column: int, dimension: int, variance: float, identifier: str):
        if not isinstance(column, int) or not isinstance(dimension, int):
            raise ValueError('column and dimension must be integers')
        if not 0 <= column < dimension or not np.isfinite(variance) or variance <= 0:
            raise ValueError('invalid column, dimension or variance')
        if not identifier:
            raise ValueError('prior identifier must be nonempty')
        self.column, self.dimension = column, dimension
        self.observation_ids = (identifier,)
        self.observation = np.zeros(1)
        # t4 variance is twice its scale matrix.
        self.covariance = np.array([[variance/2.]])
        self.jacobian = np.zeros((1, dimension))
        self.jacobian[0, column] = 1.

    def predict_selected(self, state, index):
        state = np.asarray(state, dtype=float)
        if index != 0 or state.shape != (self.dimension,) or not np.all(np.isfinite(state)):
            raise ValueError('invalid prior prediction request')
        return Prediction(state[self.column:self.column+1], self.jacobian, self.covariance)

    def score_selected(self, state, index):
        if index == 1:
            return -np.inf
        prediction = self.predict_selected(state, index)
        return student_t_logpdf(-prediction.mean, prediction.covariance, 4.)

    def score_all(self, state):
        return np.array([self.score_selected(state, 0), -np.inf])
