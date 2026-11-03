"""Conditional identity control and variance-matched satellite timing prior."""
import numpy as np

from leo.analysis.localization_prior import ScalarStudentPriorPort


class FixedOriginalPort:
    """Restrict association while retaining the original score, including background."""

    def __init__(self, base, assignment):
        self.base, self.assignment = base, assignment
        self.candidate_count = base.candidate_count
        self.observation, self.observation_ids = base.observation, base.observation_ids
        self.priors_piecewise_constant = base.priors_piecewise_constant

    def predict_selected(self, state, index):
        return self.base.predict_selected(state, index)

    def score_selected(self, state, index):
        return self.base.score_selected(state, index) if index == self.assignment else -np.inf

    def score_all(self, state):
        result = np.full(self.candidate_count+1, -np.inf)
        result[self.assignment] = self.score_selected(state, self.assignment)
        return result


def prepare_epoch_prior(ports, state, heavy):
    assignments = [int(np.argmax(p.score_all(state))) for p in ports]
    labels = sorted({i for p, i in zip(ports, assignments, strict=True) if i < p.candidate_count})
    fixed = [FixedOriginalPort(p, i) for p, i in zip(ports, assignments, strict=True)]
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    factors = []
    if heavy:
        for index in labels:
            precision[5+index] = 0.
            factors.append(ScalarStudentPriorPort(5+index, len(state), .25,
                                                   'prior:satellite-epoch:'+str(index)))
    return fixed+factors, precision, assignments, labels
