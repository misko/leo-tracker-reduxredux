"""Matched nonlinear Gaussian residual control with fixed associations."""
from dataclasses import replace

import numpy as np


class FixedGaussianPort:
    def __init__(self, base, assignment):
        if not 0 <= assignment <= base.candidate_count:
            raise ValueError('invalid fixed assignment')
        self.base, self.assignment = base, assignment
        self.candidate_count = base.candidate_count
        self.observation, self.observation_ids = base.observation, base.observation_ids
        self.priors_piecewise_constant = True
        self._key, self._prediction = None, None

    def predict_selected(self, state, index):
        if index != self.assignment or index == self.candidate_count:
            raise ValueError('prediction requires the fixed signal assignment')
        key = np.asarray(state, dtype=float).tobytes()
        if key != self._key:
            prediction = self.base.predict_selected(state, index)
            self._prediction = replace(prediction, covariance=2*prediction.covariance)
            self._key = key
        return self._prediction

    def score_selected(self, state, index):
        if index != self.assignment:
            return -np.inf
        if index == self.candidate_count:
            # Same Student-t background and visibility prior as the original
            # model. As in the linear control, background geometry uses zero
            # nuisance so the only changed dependency is signal nonlinearity.
            nominal = np.zeros_like(state)
            nominal[:2] = state[:2]
            return self.base.score_selected(nominal, index)
        prediction = self.predict_selected(state, index)
        if not prediction.eligible:
            return -np.inf
        residual = self.observation-prediction.mean
        chol = np.linalg.cholesky(prediction.covariance)
        white = np.linalg.solve(chol, residual)
        return float(np.log(self.base.config.signal_prior/self.candidate_count)
                     -.5*(len(residual)*np.log(2*np.pi)
                          +2*np.log(np.diag(chol)).sum()+white@white))

    def score_all(self, state):
        scores = np.full(self.candidate_count+1, -np.inf)
        scores[self.assignment] = self.score_selected(state, self.assignment)
        return scores
