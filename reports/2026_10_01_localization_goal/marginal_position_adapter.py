"""Explicit linear-nuisance approximation with fixed satellite assignments."""
import numpy as np

from leo.analysis.localization_marginal import integrate_shared_gaussian


class SharedPositionObjective:
    """Integrate Gaussian nuisance around zero at each nonlinear position.

    The declared model is y=f(position,0)+H(position,0)b+e, with Gaussian b
    and Gaussian e of covariance twice the baseline t4 scale (equal variance).
    Signal identity priors and the original Student-t background are included.
    Assignments come from the same fresh robust fit and remain fixed. This is
    exact integration of the local linear model, not of the nonlinear physics
    or a Student-t likelihood. The profile arm removes only the determinant
    correction, giving the matched penalized Gaussian optimum.
    """

    def __init__(self, ports, state_size, assignments, arm):
        if arm not in ('profile', 'marginal') or len(ports) != len(assignments):
            raise ValueError('invalid shared position model')
        self.ports, self.state_size = ports, state_size
        self.assignments, self.arm = tuple(assignments), arm
        self.columns = np.array([2, 3, 4, *sorted(
            {5+i for p, i in zip(ports, assignments, strict=True) if i < p.candidate_count})])
        self.sigma = np.r_[1., np.full(len(self.columns)-1, .5)]
        self.cache = {}

    def evaluate(self, position):
        position = np.asarray(position, dtype=float)
        if position.shape != (2,) or not np.all(np.isfinite(position)):
            raise ValueError('invalid position')
        key = position.tobytes()
        if key in self.cache:
            return self.cache[key]
        state = np.zeros(self.state_size)
        state[:2] = position
        if np.linalg.norm(position) > 250.:
            return np.inf, state
        blocks, log_prior_background = [], 0.
        for port, index in zip(self.ports, self.assignments, strict=True):
            if index == port.candidate_count:
                log_prior_background += port.score_selected(state, index)
                continue
            prediction = port.predict_selected(state, index)
            if not prediction.eligible:
                return np.inf, state
            blocks.append((port.observation-prediction.mean,
                           prediction.jacobian[:, self.columns], 2*prediction.covariance))
            log_prior_background += np.log(port.config.signal_prior/port.candidate_count)
        result = integrate_shared_gaussian(blocks, self.sigma)
        score = result.log_likelihood+log_prior_background
        if self.arm == 'profile':
            score += np.log(np.diag(result.whitened_information_cholesky)).sum()
        state[self.columns] = result.nuisance_mean
        self.cache[key] = float(-score), state
        return self.cache[key]

    def __call__(self, position):
        return self.evaluate(position)[0]
