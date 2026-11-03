"""Fixed-nuisance spatial objective using disjoint track and candidate evidence."""
# ruff: noqa: I001
import copy
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from run_split_expansion import prepare
from acquire import LIGHT_KM_S, enu_state_ecef_km
from physics import _noise_covariance
from regression_batch import digest
from leo.analysis.localization_candidate_set import wrapped_cauchy_pdf, candidate_set_log_ratio

HERE = Path(__file__).resolve().parent


class CandidateSpatialObjective:
    def __init__(self, unit, *, state=None, assignments=None):
        self.scan, self.height, self.ports = prepare(unit)
        self.parent_path = HERE/'split-expansion-fit-v1'/(unit+'.json')
        seal = json.loads(self.parent_path.with_suffix('.seal.json').read_text())
        assert digest(self.parent_path) == seal['prediction_sha256']
        self.parent = json.loads(self.parent_path.read_text())
        self.initial = np.asarray(self.parent['best']['mean'] if state is None else state).copy()
        if self.initial.shape != np.asarray(self.parent['best']['mean']).shape:
            raise ValueError('state shape differs from frozen parent')
        if not np.all(np.isfinite(self.initial)):
            raise ValueError('nonfinite state')
        self.assignments = ([int(np.argmax(p.score_all(self.initial))) for p in self.ports]
                            if assignments is None else list(assignments))
        if len(self.assignments) != len(self.ports):
            raise ValueError('assignment count differs from track count')
        if any(not 0 <= i <= p.candidate_count for i, p in
               zip(self.assignments, self.ports, strict=True)):
            raise ValueError('assignment outside catalogue')
        source = json.loads((HERE/'source-split-expansion-v1'/(unit+'.json')).read_text())
        grouped = defaultdict(list)
        for p in source['checking_points']:
            grouped[p['source_group_id']].append(p)
        self.groups = []
        for key, points in sorted(grouped.items()):
            p = points[0]
            scale = 11.2e9/p['actual_rf_hz']
            self.groups.append(dict(id=key, rx=p['receiver_id'], channel=p['channel'],
                rf=p['actual_rf_hz'], period=scale/4.4e-6,
                time=float(np.median([(q['support_center_utc_ns']-source['start_utc_ns'])/1e9
                                      for q in points])),
                candidates=np.array([q['measured_cfo_hz']*scale for q in points])))
        self.prepared = []
        group_slots = [[] for _ in self.groups]
        slots = 0
        for (_, track), port, index in zip(self.scan.tracks, self.ports,
                                           self.assignments, strict=True):
            if index == port.candidate_count:
                continue
            selected = [track.observation_ids.index(v) for v in port.observation_ids]
            train_times = track.times_s[selected]
            rx = int(track.receiver_indices[0])
            channel = int(track.observation_ids[0].split(':channel')[1].split(':')[0])
            eligible = [i for i, g in enumerate(self.groups) if g['rx'] == rx
                        and g['channel'] == channel and g['rf'] == track.rf_hz
                        and track.times_s[0] <= g['time'] <= track.times_s[-1]]
            query = copy.copy(port.likelihood)
            query.bank = port._row_bank(index)
            query.times = np.r_[train_times, [self.groups[i]['time'] for i in eligible]]
            position, velocity = query._orbit_states_per_satellite(
                [self.initial[2]+self.initial[5+index]])
            weights = np.linalg.solve(_noise_covariance(train_times, self.scan.config),
                                      np.ones(len(train_times)))
            weights /= weights.sum()
            drift = (self.initial[3+rx]*port.likelihood.drift_scale
                     *(query.times-train_times.mean()))
            self.prepared.append((position[0], velocity[0], drift, weights,
                                  track.frequencies_hz[selected], len(train_times)))
            for i in eligible:
                group_slots[i].append(slots)
                slots += 1
        self.group_slots = group_slots
        pair_groups, pair_slots, values = [], [], []
        for i, (g, ix) in enumerate(zip(self.groups, group_slots, strict=True)):
            for y in g['candidates']:
                for slot in ix:
                    pair_groups.append(i)
                    pair_slots.append(slot)
                    values.append(y)
        self.pair_groups = np.asarray(pair_groups, dtype=int)
        self.pair_slots = np.asarray(pair_slots, dtype=int)
        self.values = np.asarray(values)
        self.periods = np.array([g['period'] for g in self.groups])
        self.pair_periods = self.periods[self.pair_groups]
        self.counts = np.bincount(self.pair_groups, minlength=len(self.groups))
        self.calls = 0

    def predictions(self, point):
        receiver = enu_state_ecef_km(*point, self.height(*point),
            self.scan.config.prior_center_lat_deg, self.scan.config.prior_center_lon_deg)
        out = []
        factor = self.scan.config.doppler_sign*self.scan.config.reference_frequency_hz/LIGHT_KM_S
        for position, velocity, drift, weights, measured, n in self.prepared:
            line = position-receiver
            line /= np.linalg.norm(line, axis=1, keepdims=True)
            mean = factor*np.sum(velocity*line, axis=1)+drift
            offset = weights@(measured-mean[:n])
            out.extend(mean[n:]+offset)
        return np.asarray(out)

    def components(self, point):
        self.calls += 1
        state = self.initial.copy()
        state[:2] = point
        precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
        train = float(.5*(precision*state)@state-sum(p.score_selected(state, i)
            for p, i in zip(self.ports, self.assignments, strict=True)))
        means = self.predictions(point)
        residual = self.values-means[self.pair_slots]
        density = np.zeros_like(residual)
        for period in np.unique(self.pair_periods):
            mask = self.pair_periods == period
            density[mask] = wrapped_cauchy_pdf(residual[mask], period, 200.)
        sums = np.bincount(self.pair_groups, weights=density, minlength=len(self.groups))
        ratios = np.ones(len(self.groups))
        mask = self.counts > 0
        ratios[mask] = .5+.5*self.periods[mask]*sums[mask]/self.counts[mask]
        return train, float(np.log(ratios).sum())

    def __call__(self, point):
        train, additional = self.components(point)
        return train-additional

    def check_parity(self):
        train, packed = self.components(self.initial[:2])
        assert abs(train-self.parent['best']['objectives'][-1]) < 1e-6
        means = self.predictions(self.initial[:2])
        scalar = sum(candidate_set_log_ratio(g['candidates'], means[ix],
            period=g['period'], scale=200., signal_probability=.5)
            for g, ix in zip(self.groups, self.group_slots, strict=True))
        assert abs(scalar-packed) < 1e-8
        return dict(training_difference=train-self.parent['best']['objectives'][-1],
                    packed_scalar_difference=packed-scalar)
