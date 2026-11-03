"""Research adapter for coherent slope versus trace-matched noise controls."""
import time
from dataclasses import replace

import numpy as np
from acquisition_dot import AcquisitionResult, DotTrackLikelihood, Seed, coarse_to_fine

from leo.analysis.localization_discrepancy import slope_discrepancy_scale
from leo.analysis.localization_search import MemoizedPointScorer


class DiscrepancyLikelihood(DotTrackLikelihood):
    def __init__(self, *args, sigma=0., isotropic_control=False, **kwargs):
        super().__init__(*args, **kwargs)
        design = self.contrasts@(self.centered_times*self.drift_scale)
        self.covariance = slope_discrepancy_scale(
            self.covariance, design, sigma, isotropic_control=isotropic_control)
        self.precision = np.linalg.inv(self.covariance)
        self.log_normalizer = -.5*(self.observation.size*np.log(2*np.pi)
                                   +np.linalg.slogdet(self.covariance)[1])
        # Background is a separate normalized alternative, kept fixed across
        # arms. Only the physical-signal residual scale changes.


class DiscrepancyPort:
    def __init__(self, base, likelihood):
        self.base = base
        self.likelihood = likelihood
        self.observation = base.observation
        self.observation_ids = base.observation_ids
        self.candidate_count = base.candidate_count
        self.priors_piecewise_constant = True
        self._key, self._scores = None, None

    def score_all(self, state):
        key = np.asarray(state, dtype=float).tobytes()
        if key != self._key:
            self._scores = self.likelihood.branch_loglik_at_state(state)
            self._key = key
        return self._scores

    def score_selected(self, state, index):
        return float(self.score_all(state)[index])

    def predict_selected(self, state, index):
        prediction = self.base.predict_selected(state, index)
        return replace(prediction, covariance=self.likelihood.covariance)


def make_ports(scan, height, bases, *, sigma, isotropic_control):
    cache = {}
    return [DiscrepancyPort(base, DiscrepancyLikelihood(
        track, scan.bank, scan.config, height, 4., geometry_cache=cache,
        sigma=sigma, isotropic_control=isotropic_control))
        for base, (_, track) in zip(bases, scan.tracks, strict=True)]


def propose(ports, *, deadline):
    started = time.monotonic()

    def score(points):
        total = np.zeros(len(points))
        for begin in range(0, len(points), 32):
            if time.monotonic() >= deadline:
                raise TimeoutError('discrepancy acquisition budget exhausted')
            for port in ports:
                values = port.likelihood(points[begin:begin+32], np.empty((1, 0)))[:, 0, :]
                maximum = values.max(axis=1)
                total[begin:begin+len(values)] += maximum+np.log(
                    np.exp(values-maximum[:, None]).sum(axis=1))
        return total

    cached = MemoizedPointScorer(score)
    seeds, scores, requested, spacing = coarse_to_fine(cached)
    proposal = AcquisitionResult(tuple(
        Seed(float(p[0]), float(p[1]), float(s))
        for p, s in zip(seeds, scores, strict=True)),
        requested, len(ports), spacing, time.monotonic()-started)
    return proposal, dict(requested_points=requested, unique_points=cached.evaluated_points)
