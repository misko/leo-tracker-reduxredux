"""Joint position and shared-nuisance derivative adapter for candidate evidence."""
# ruff: noqa: I001
import copy
import json
from pathlib import Path
from regression_batch import digest, verify_sources

import numpy as np
from offset_marginal_density import density
from candidate_spatial_expansion_adapter import CandidateSpatialObjective
from acquire import LIGHT_KM_S, enu_state_ecef_km
from physics import _noise_covariance
from leo.analysis.localization_candidate_derivatives import (
    candidate_set_derivatives, profile_offset_jacobian,
)
from leo.analysis.localization_candidate_set import candidate_set_log_ratio


class CandidateJointObjective:
    def __init__(self, unit):
        path = Path(__file__).resolve().parent/'offset-marginal-calibration-v2.json'
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        calibration = json.loads(path.read_text())
        verify_sources(calibration['source_sha256'])
        verify_sources(calibration['input_sha256'])
        fold = next(f for f in calibration['folds'] if f['dataset'] == unit.split('-')[0])
        assert all(u.split('-')[0] != unit.split('-')[0] for u in fold['donors'])
        self.parameters = fold['chosen']
        self.base = CandidateSpatialObjective(unit)
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
        conditionals = []
        for port, index in zip(b.ports, b.assignments, strict=True):
            value -= port.score_selected(state, index)
            if index < port.candidate_count:
                prediction = port.predict_selected(state, index)
                residual = port.observation-prediction.mean
                solved = np.linalg.solve(prediction.covariance, residual)
                weight = (4+len(residual))/(4+float(residual@solved))
                q_gradient = -2*prediction.jacobian[:, self.columns].T@solved
                if gradient:
                    grad += .5*weight*q_gradient
                conditionals.append((float(residual@solved), q_gradient))
        receiver = self.receiver(state[:2])
        if gradient:
            receiver_jacobian = np.column_stack([
                (self.receiver(state[:2]+d)-self.receiver(state[:2]-d))/.002
                for d in np.eye(2)*.001])
        means, jacobians, scales, degrees, scale_jacobians = [], [], [], [], []
        factor = b.scan.config.doppler_sign*b.scan.config.reference_frequency_hz/LIGHT_KM_S
        for (query, index, rx, n, weights, measured, center), (q, q_gradient) in zip(self.prepared, conditionals, strict=True):
            training_times = query.times[:n]
            ones = np.ones(n)
            offset_precision = float(ones@np.linalg.solve(_noise_covariance(training_times, b.scan.config), ones))
            df = 4+n-1
            offset_scale = np.sqrt((4+q)/(df*offset_precision))
            scales.extend([offset_scale]*(len(query.times)-n))
            degrees.extend([df]*(len(query.times)-n))
            scale_jacobians.extend([offset_scale/(2*(4+q))*q_gradient]*(len(query.times)-n))
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
            if not slots or not len(group['candidates']):
                continue
            total = 0.
            total_gradient = np.zeros(len(reduced))
            for slot in slots:
                residual = group['candidates']-means[slot]
                pdf, dr, ds = density(residual, group['period'], scales[slot], degrees[slot],
                                      self.parameters['noise_hz'], derivatives=gradient)
                total += float(pdf.sum())
                if gradient:
                    total_gradient += -float(dr.sum())*jacobians[slot]+float(ds.sum())*scale_jacobians[slot]
            factor = self.parameters['probability']*group['period']/(len(slots)*len(group['candidates']))
            ratio = 1-self.parameters['probability']+factor*total
            value -= candidate_weight*np.log(ratio)
            if gradient:
                grad -= candidate_weight*factor/ratio*total_gradient
        return value, grad if gradient else None
