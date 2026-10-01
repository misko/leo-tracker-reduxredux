"""One fixed group branch with shared Student-t residual scale."""
import numpy as np
from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.robust_likelihood import student_t_logpdf


class SharedScalePort:
    candidate_count = 1
    priors_piecewise_constant = True

    def __init__(self, members):
        self.members = tuple(members)
        if not self.members or any(not 0 <= i < p.candidate_count for p, i in self.members):
            raise ValueError('nonempty signal group required')
        self.observation_ids = tuple(v for p, _ in self.members for v in p.observation_ids)
        if len(set(self.observation_ids)) != len(self.observation_ids): raise ValueError('duplicate observations')
        self.observation = np.concatenate([p.observation for p, _ in self.members])

    def predict_selected(self, state, index):
        if index != 0: raise ValueError('fixed group branch required')
        predictions = [p.predict_selected(state, i) for p, i in self.members]
        n = sum(len(p.mean) for p in predictions); covariance = np.zeros((n, n)); offset = 0
        for p in predictions:
            end = offset+len(p.mean); covariance[offset:end, offset:end] = p.covariance; offset = end
        return Prediction(np.concatenate([p.mean for p in predictions]), np.vstack([p.jacobian for p in predictions]),
                          covariance, all(p.eligible for p in predictions))

    def score_selected(self, state, index):
        if index != 0: raise ValueError('fixed group branch required')
        if len(self.members) == 1:
            p, i = self.members[0]; return p.score_selected(state, i)
        total = 0.
        for p, i in self.members:
            physical = p.score_selected(state, i)
            if not np.isfinite(physical): return physical
            pred = p.predict_selected(state, i)
            if not pred.eligible: return -np.inf
            total += physical-student_t_logpdf(p.observation-pred.mean, pred.covariance, 4.)
        prediction = self.predict_selected(state, 0)
        return float(total+student_t_logpdf(self.observation-prediction.mean, prediction.covariance, 4.))

    def score_all(self, state): return np.array([self.score_selected(state, 0), -np.inf])
