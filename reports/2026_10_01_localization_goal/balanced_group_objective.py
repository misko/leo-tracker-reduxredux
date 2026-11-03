"""Fixed-identity satellite-balanced composite score, not a normalized density."""
from collections import Counter

import numpy as np

from fixed_reference_nuisance import ConditionalObjective


def group_weights(labels):
    counts = Counter(label for label in labels if label is not None)
    total = sum(counts.values())
    return np.array([total/(len(counts)*counts[label]) if label is not None else 1.
                     for label in labels])


class BalancedGroupObjective(ConditionalObjective):
    def __init__(self, unit, arm):
        super().__init__(unit, 'control')
        self.columns = np.array([0, 1, 2, 3, 4, *self.epochs])
        labels = [i if i < p.candidate_count else None
                  for p, i in zip(self.ports, self.assignments, strict=True)]
        self.weights = group_weights(labels) if arm == 'balanced' else np.ones(len(labels))

    def evaluate(self, reduced, gradient=True):
        state = self.initial.copy()
        state[self.columns] = reduced
        value = float(.5*(self.precision*state)@state)
        grad = (self.precision*state)[self.columns]
        for port, identity, coefficient in zip(self.ports, self.assignments, self.weights, strict=True):
            value -= coefficient*port.score_selected(state, identity)
            if gradient and identity < port.candidate_count:
                prediction = port.predict_selected(state, identity)
                residual = port.observation-prediction.mean
                solved = np.linalg.solve(prediction.covariance, residual)
                weight = (4+len(residual))/(4+float(residual@solved))
                grad -= coefficient*weight*prediction.jacobian[:, self.columns].T@solved
        return value, grad if gradient else None

    def metric(self):
        matrix = np.diag(self.precision[self.columns])
        for port, identity, coefficient in zip(self.ports, self.assignments, self.weights, strict=True):
            if identity == port.candidate_count:
                continue
            prediction = port.predict_selected(self.initial, identity)
            residual = port.observation-prediction.mean
            solved = np.linalg.solve(prediction.covariance, residual)
            weight = (4+len(residual))/(4+float(residual@solved))
            j = prediction.jacobian[:, self.columns]
            matrix += coefficient*weight*j.T@np.linalg.solve(prediction.covariance, j)
        return (matrix+matrix.T)/2
