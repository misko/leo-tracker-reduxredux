"""Research adapter for frozen evidence; numerical analyzers see only ports.

Selected-satellite prediction reuses the frozen physics on a one-row orbit view.
Full-catalogue scoring and global orbit support semantics remain unchanged.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / '2026_10_01_fixed_height_greedy'
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(HERE.parent / '2026_09_30_broad_prior_acquisition'))
from common import load_scan
from orbit_input import use_extended_orbits
from geoid import load_height_model
from acquire import FixedHeightTrackLikelihood, propose
from physics_fixed import build_fixed_height_factor
from physics import OrbitBank, StateLayout, _spread_indices
from leo.analysis.gaussian_sum_location import Prediction

for _module, _expected in {
    'common': HERE.parent / '2026_09_30_broad_prior_acquisition/common.py',
    'orbit_input': OLD / 'orbit_input.py', 'geoid': OLD / 'geoid.py',
    'acquire': OLD / 'acquire.py', 'physics_fixed': OLD / 'physics_fixed.py',
    'physics': HERE.parent / '2026_09_30_gaussian_sum_64_scan/physics.py',
}.items():
    if Path(sys.modules[_module].__file__).resolve() != _expected.resolve():
        raise ImportError(f'wrong frozen module bound for {_module}')


class TrackPort:
    def __init__(self, track, bank, layout, config, height, *, predictor='selected'):
        if tuple(bank.norad_ids) != tuple(layout.norad_ids):
            raise ValueError('bank/layout ordering must match')
        if predictor not in ('selected', 'oracle'):
            raise ValueError('unknown predictor')
        self.track, self.bank, self.layout = track, bank, layout
        self.config, self.height, self.predictor = config, height, predictor
        self.likelihood = FixedHeightTrackLikelihood(track, bank, config, height, degrees_of_freedom=4.)
        selected = _spread_indices(track.times_s, config.max_points)
        self.observation_ids = tuple(track.observation_ids[i] for i in selected)
        self.observation = self.likelihood.observation
        self.candidate_count = len(bank.norad_ids)
        self.priors_piecewise_constant = True
        self._score_key, self._scores = None, None
        self._full_factor = None
        self._row_factors = {}
        self._row_likelihoods = {}
        self.calls = dict(score_requests=0, score_evaluations=0, selected_scores=0, jacobians=0)

    def score_all(self, state):
        self.calls['score_requests'] += 1
        state = np.asarray(state, dtype=float)
        if state.shape != (5 + self.candidate_count,) or not np.all(np.isfinite(state)):
            raise ValueError('invalid state')
        key = state.tobytes()
        if key != self._score_key:
            values = self.likelihood.branch_loglik_at_state(state)
            values.setflags(write=False)
            self._score_key, self._scores = key, values
            self.calls['score_evaluations'] += 1
        return self._scores

    def _global_support(self, state, *, derivatives=True):
        for clock_step in ((0., 1e-4, -1e-4) if derivatives else (0.,)):
            clock = state[2] + clock_step
            lower = (self.likelihood.times.min() + clock) + state[5:]
            upper = (self.likelihood.times.max() + clock) + state[5:]
            if np.any(lower < self.bank.times_s[1]) or np.any(upper > self.bank.times_s[-2]):
                raise ValueError('prediction time lacks global four-knot orbit support')

    def _row_bank(self, index):
        return OrbitBank((self.bank.norad_ids[index],), self.bank.times_s,
            self.bank.positions_ecef_km[index:index+1], self.bank.velocities_ecef_km_s[index:index+1])

    def score_selected(self, state, index):
        state = np.asarray(state, dtype=float)
        if state.shape != (5 + self.candidate_count,) or not np.all(np.isfinite(state)):
            raise ValueError('invalid state')
        if not 0 <= index <= self.candidate_count:
            raise ValueError('invalid branch')
        self.calls['selected_scores'] += 1
        if index == self.candidate_count:
            return float(self.score_all(state)[index])
        self._global_support(state)
        if index not in self._row_likelihoods:
            self._row_likelihoods[index] = FixedHeightTrackLikelihood(
                self.track, self._row_bank(index), self.config, self.height, degrees_of_freedom=4.)
        columns = np.r_[np.arange(5), 5 + index]
        return float(self._row_likelihoods[index].branch_loglik_at_state(state[columns])[0]
                     - np.log(self.candidate_count))

    def oracle_factor(self):
        if self._full_factor is None:
            built = build_fixed_height_factor(self.track, self.bank, self.layout, self.config, self.height)
            self._full_factor = replace(built.factor,
                background_log_likelihood=self.likelihood.background_log_likelihood)
        return self._full_factor

    def predict_selected(self, state, index):
        state = np.asarray(state, dtype=float)
        if state.shape != (5 + self.candidate_count,) or not np.all(np.isfinite(state)):
            raise ValueError('invalid state')
        if not 0 <= index < self.candidate_count:
            raise ValueError('prediction requires a satellite branch')
        self.calls['jacobians'] += 1
        if self.predictor == 'oracle':
            return self.oracle_factor().candidates[index].predict(state)
        # Frozen finite differences change the shared clock by +/-1e-4 seconds.
        # Other, unselected catalogue entries must still have support, as before.
        self._global_support(state)
        if index not in self._row_factors:
            identifier = self.bank.norad_ids[index]
            bank = self._row_bank(index)
            self._row_factors[index] = build_fixed_height_factor(
                self.track, bank, StateLayout((identifier,)), self.config, self.height).factor
        columns = np.r_[np.arange(5), 5 + index]
        prediction = self._row_factors[index].candidates[0].predict(state[columns])
        jacobian = np.zeros((self.observation.size, state.size))
        jacobian[:, columns] = prediction.jacobian
        return Prediction(prediction.mean, jacobian, prediction.covariance, prediction.eligible)


def prepare(unit, *, predictor='selected'):
    scan = use_extended_orbits(load_scan(unit))
    height = load_height_model()
    ports = [TrackPort(obs, scan.bank, scan.layout, scan.config, height, predictor=predictor)
             for _, obs in scan.tracks]
    return scan, height, ports
