"""Fixed identity sample-mixture port; EM curvature, exact normalized scores."""
from dataclasses import replace

import numpy as np
from physics import helmert_contrasts

from leo.analysis.localization_sample_mixture import SampleVarianceMixture


class SampleMixturePort:
    def __init__(self, base, assignment, probability):
        self.base, self.assignment, self.probability = base, assignment, probability
        self.candidate_count = base.candidate_count
        self.observation, self.observation_ids = base.observation, base.observation_ids
        self.priors_piecewise_constant = True
        indices = [base.track.observation_ids.index(i) for i in self.observation_ids]
        self.contrasts = helmert_contrasts(base.track.receiver_indices[indices])
        self._key = None
        self.mixture = None
        self.posterior_inflated = None

    def _evaluate(self, state):
        key = np.asarray(state, dtype=float).tobytes()
        if key == self._key:
            return
        original = self.base.predict_selected(state, self.assignment)
        if self.mixture is None:
            self.original_covariance = original.covariance.copy()
            self.mixture = SampleVarianceMixture(original.covariance, self.contrasts,
                                                 self.probability, 1000.**2)
        np.testing.assert_array_equal(original.covariance, self.original_covariance)
        score, precision, self.posterior_inflated = self.mixture.evaluate(
            self.observation-original.mean)
        covariance = np.linalg.solve(precision, np.eye(len(self.observation)))
        self.prediction = replace(original, covariance=.5*(covariance+covariance.T))
        self.score = (score+np.log(self.base.config.signal_prior/self.candidate_count)
                      if original.eligible else -np.inf)
        self._key = key

    def predict_selected(self, state, index):
        if index != self.assignment or index == self.candidate_count:
            raise ValueError('fixed signal assignment required')
        self._evaluate(state)
        return self.prediction

    def score_selected(self, state, index):
        if index != self.assignment:
            return -np.inf
        if index == self.candidate_count:
            return self.base.score_selected(state, index)
        self._evaluate(state)
        return self.score

    def score_all(self, state):
        result = np.full(self.candidate_count+1, -np.inf)
        result[self.assignment] = self.score_selected(state, self.assignment)
        return result
