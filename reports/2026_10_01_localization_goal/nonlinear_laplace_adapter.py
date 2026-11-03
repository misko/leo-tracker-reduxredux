"""Local original-model derivatives and a fixed-position nuisance fit port."""
from dataclasses import replace

import numpy as np

from leo.analysis.localization_observed import gradient_jacobian


def observed_information(ports, assignments, state, columns, step=.005):
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    information = np.diag(precision[columns])
    for port, index in zip(ports, assignments, strict=True):
        if index == port.candidate_count:
            continue
        local = np.array([0, 1, 2, 3, 4, 5+index])
        selected = np.array([c for c in local if c in columns])
        slots = np.array([np.flatnonzero(columns == c)[0] for c in selected])

        def gradient(values, port=port, index=index, selected=selected):
            trial = state.copy()
            trial[selected] = values
            prediction = port.predict_selected(trial, index)
            if not prediction.eligible:
                raise ValueError('Hessian probe outside eligible signal branch')
            residual = port.observation-prediction.mean
            solved = np.linalg.solve(prediction.covariance, residual)
            weight = (4+len(residual))/(4+residual@solved)
            return -weight*prediction.jacobian[:, selected].T@solved

        information[np.ix_(slots, slots)] += gradient_jacobian(
            gradient, state[selected], np.full(len(selected), step))
    return .5*(information+information.T)


def laplace_score(ports, assignments, state, columns):
    information = observed_information(ports, assignments, state, columns)
    chol = np.linalg.cholesky(information)
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    profile = .5*(precision*state)@state-sum(
        p.score_selected(state, i) for p, i in zip(ports, assignments, strict=True))
    logdet = 2*np.log(np.diag(chol)).sum()
    return float(profile+.5*logdet), float(profile), float(logdet)


class FixedNuisancePort:
    """Keep original fixed-branch scores; remove position from optimization."""

    def __init__(self, base, assignment, position):
        self.base, self.assignment = base, assignment
        self.position = np.asarray(position)
        self.candidate_count = base.candidate_count
        self.observation, self.observation_ids = base.observation, base.observation_ids
        self.priors_piecewise_constant = True

    def _state(self, state):
        result = np.array(state, dtype=float)
        result[:2] = self.position
        return result

    def predict_selected(self, state, index):
        prediction = self.base.predict_selected(self._state(state), index)
        jacobian = prediction.jacobian.copy()
        jacobian[:, :2] = 0.
        return replace(prediction, jacobian=jacobian)

    def score_selected(self, state, index):
        if index != self.assignment:
            return -np.inf
        return self.base.score_selected(self._state(state), index)

    def score_all(self, state):
        result = np.full(self.candidate_count+1, -np.inf)
        result[self.assignment] = self.score_selected(state, self.assignment)
        return result
