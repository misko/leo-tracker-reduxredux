"""Joint position and shared-nuisance derivative adapter for candidate evidence."""
# ruff: noqa: I001
import copy

import numpy as np
from candidate_cached_spatial import CandidateSpatialObjective
from acquire import LIGHT_KM_S, enu_state_ecef_km
from physics import _noise_covariance
from leo.analysis.localization_candidate_derivatives import (
    candidate_set_derivatives, profile_offset_jacobian,
)
from leo.analysis.localization_candidate_set import candidate_set_log_ratio


class CandidateJointObjective:
    def __init__(self, unit, *, state=None, assignments=None, context=None):
        self.base = CandidateSpatialObjective(unit, state=state, assignments=assignments,
                                               context=context)
        b = self.base
        epochs = sorted({5+i for p, i in zip(b.ports, b.assignments, strict=True)
                         if i < p.candidate_count})
        self.columns = np.array([0, 1, 2, 3, 4, *epochs])
        self.initial = b.initial[self.columns].copy()
        self.prepared = []
        for (_, track), port, index in zip(b.scan.tracks, b.ports, b.assignments, strict=True):
            if index == port.candidate_count:
                continue
            selected = [track.observation_ids.index(v) for v in port.observation_ids]
            times = track.times_s[selected]
            rx = int(track.receiver_indices[0])
            channel = int(track.observation_ids[0].split(':channel')[1].split(':')[0])
            eligible = [i for i, g in enumerate(b.groups) if g['rx'] == rx
                        and g['channel'] == channel and g['rf'] == track.rf_hz
                        and track.times_s[0] <= g['time'] <= track.times_s[-1]]
            query = copy.copy(port.likelihood)
            query.bank = port._row_bank(index)
            query.times = np.r_[times, [b.groups[i]['time'] for i in eligible]]
            weights = np.linalg.solve(_noise_covariance(times, b.scan.config), np.ones(len(times)))
            weights /= weights.sum()
            self.prepared.append((query, index, rx, len(times), weights,
                                  track.frequencies_hz[selected], times.mean()))

    def receiver(self, point):
        b = self.base
        return enu_state_ecef_km(*point, b.height(*point),
            b.scan.config.prior_center_lat_deg, b.scan.config.prior_center_lon_deg)

    def evaluate(self, reduced, *, gradient=True, candidate_weight=1.):
        b = self.base
        state = b.initial.copy()
        state[self.columns] = reduced
        precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
        value = float(.5*(precision*state)@state)
        grad = (precision*state)[self.columns]
        for port, index in zip(b.ports, b.assignments, strict=True):
            value -= port.score_selected(state, index)
            if gradient and index < port.candidate_count:
                prediction = port.predict_selected(state, index)
                residual = port.observation-prediction.mean
                solved = np.linalg.solve(prediction.covariance, residual)
                weight = (4+len(residual))/(4+float(residual@solved))
                grad -= weight*prediction.jacobian[:, self.columns].T@solved
        receiver = self.receiver(state[:2])
        if gradient:
            receiver_jacobian = np.column_stack([
                (self.receiver(state[:2]+d)-self.receiver(state[:2]-d))/.002
                for d in np.eye(2)*.001])
        means, jacobians = [], []
        factor = b.scan.config.doppler_sign*b.scan.config.reference_frequency_hz/LIGHT_KM_S
        for query, index, rx, n, weights, measured, center in self.prepared:
            timing = state[2]+state[5+index]

            def doppler(offset, query=query):
                position, velocity = query._orbit_states_per_satellite([offset])
                delta = position[0]-receiver
                ranges = np.linalg.norm(delta, axis=1)
                unit = delta/ranges[:, None]
                rate = np.sum(velocity[0]*unit, axis=1)
                return factor*rate, velocity[0], unit, ranges, rate

            frequency, velocity, line, ranges, rate = doppler(timing)
            drift_basis = query.drift_scale*(query.times-center)
            raw = frequency+state[3+rx]*drift_basis
            means.extend(raw[n:]+weights@(measured-raw[:n]))
            if gradient and len(raw) > n:
                j = np.zeros((len(raw), len(self.columns)))
                j[:, :2] = (factor*(rate[:, None]*line-velocity)/ranges[:, None])@receiver_jacobian
                timing_jacobian = (doppler(timing+1e-4)[0]-doppler(timing-1e-4)[0])/2e-4
                j[:, 2] = timing_jacobian
                j[:, int(np.flatnonzero(self.columns == 5+index)[0])] = timing_jacobian
                j[:, 3+rx] = drift_basis
                jacobians.extend(profile_offset_jacobian(j, n, weights))
        means = np.asarray(means)
        if gradient:
            jacobians = np.asarray(jacobians)
        for group, slots in zip(b.groups, b.group_slots, strict=True):
            if gradient:
                score, mean_gradient, _ = candidate_set_derivatives(
                    group['candidates'], means[slots], period=group['period'], scale=200.)
                if slots:
                    grad -= candidate_weight*mean_gradient@jacobians[slots]
            else:
                score = candidate_set_log_ratio(group['candidates'], means[slots],
                                                period=group['period'], scale=200.)
            value -= candidate_weight*score
        return value, grad if gradient else None
