"""A normalized Student-t block with one latent precision shared by tracks.

For a fixed identity group, lambda ~ Gamma(nu/2, nu/2) and residuals
r_i | lambda ~ N(0, C_i/lambda) independently. Integrating lambda yields a
joint Student-t with block-diagonal scale. This shares residual amplitude
uncertainty, not a coherent signed orbit error or an association posterior.
"""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import lgamma

import numpy as np

from leo.analysis.gaussian_sum_location import Prediction


@dataclass(frozen=True)
class SelectedResidualBlock:
    observation: np.ndarray
    observation_ids: tuple[str, ...]
    scale: np.ndarray
    predict: Callable[[np.ndarray], Prediction]
    log_identity_prior: float


class SharedScalePort:
    """One fixed joint signal hypothesis, exposed as one optimizer branch.

    Cholesky whitening avoids constructing a block-diagonal scale matrix.
    The whitening determinant remains in the density, preserving its original
    observation-space normalization. The supplied scales must be state-constant.
    """

    candidate_count = 1
    priors_piecewise_constant = True

    def __init__(self, blocks: Sequence[SelectedResidualBlock], nu: float = 4.):
        if not blocks or not np.isfinite(nu) or nu <= 0:
            raise ValueError('nonempty blocks and positive degrees of freedom required')
        self.blocks, self.nu = tuple(blocks), nu
        self.observation_ids = tuple(i for b in blocks for i in b.observation_ids)
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError('physical observations must not be reused')
        self.cholesky = []
        observations, normalizer = [], 0.
        for block in blocks:
            y, c = np.asarray(block.observation), np.asarray(block.scale)
            if (y.ndim != 1 or y.size == 0 or c.shape != (y.size, y.size)
                    or not np.all(np.isfinite(y)) or not np.all(np.isfinite(c))
                    or not np.allclose(c, c.T) or not np.isfinite(block.log_identity_prior)):
                raise ValueError('invalid shared residual block')
            chol = np.linalg.cholesky(c)
            self.cholesky.append(chol)
            observations.append(np.linalg.solve(chol, y))
            normalizer += block.log_identity_prior-np.log(np.diag(chol)).sum()
        self.observation = np.concatenate(observations)
        d = self.observation.size
        self.scale = np.eye(d)
        self.normalizer = float(normalizer+lgamma((nu+d)/2)-lgamma(nu/2)
                                -.5*d*np.log(nu*np.pi))
        self._key, self._prediction = None, None

    def predict_selected(self, state, index):
        if index != 0:
            raise ValueError('only the fixed joint signal has a prediction')
        key = np.asarray(state, dtype=float).tobytes()
        if key != self._key:
            means, jacobians, eligible = [], [], True
            for block, chol in zip(self.blocks, self.cholesky, strict=True):
                p = block.predict(state)
                if not np.array_equal(p.covariance, block.scale):
                    raise ValueError('shared scale model requires state-constant block scales')
                means.append(np.linalg.solve(chol, p.mean))
                jacobians.append(np.linalg.solve(chol, p.jacobian))
                eligible = eligible and p.eligible
            self._prediction = Prediction(np.concatenate(means), np.vstack(jacobians),
                                          self.scale, eligible)
            self._key = key
        return self._prediction

    def score_selected(self, state, index):
        if index == 1:
            return -np.inf
        prediction = self.predict_selected(state, index)
        if not prediction.eligible:
            return -np.inf
        residual = self.observation-prediction.mean
        return float(self.normalizer-.5*(self.nu+len(residual))*np.log1p(
            (residual@residual)/self.nu))

    def score_all(self, state):
        return np.array([self.score_selected(state, 0), -np.inf])
