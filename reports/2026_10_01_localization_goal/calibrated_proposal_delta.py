"""Exact fixed-state single-track replacements; rebuild after continuous moves."""
import copy

import numpy as np

from candidate_calibrated_cached_joint import LIGHT_KM_S
from physics import _noise_covariance
from leo.analysis.localization_candidate_set import wrapped_cauchy_pdf
from leo.analysis.localization_epoch_profile import profile_unused_epochs


class ProposalDelta:
    def __init__(self, model):
        self.model, self.base = model, model.base
        b = self.base
        self.state = b.initial.copy()
        self.assignments = list(b.assignments)
        self.training, self.additional = b.components(self.state[:2])
        self.value = self.training-self.additional
        self.scores = [p.score_selected(self.state, i)
                       for p, i in zip(b.ports, self.assignments, strict=True)]
        self.receiver = model.receiver(self.state[:2])
        self.eligible, self.support = [], []
        self.contributions = [{} for _ in b.groups]
        means, offset = b.predictions(self.state[:2]), 0
        for k, ((_, track), port, identity) in enumerate(zip(
                b.scan.tracks, b.ports, self.assignments, strict=True)):
            rx = int(track.receiver_indices[0])
            channel = int(track.observation_ids[0].split(':channel')[1].split(':')[0])
            eligible = [j for j, g in enumerate(b.groups) if g['rx'] == rx
                        and g['channel'] == channel and g['rf'] == track.rf_hz
                        and track.times_s[0] <= g['time'] <= track.times_s[-1]]
            self.eligible.append(eligible)
            selected = [track.observation_ids.index(v) for v in port.observation_ids]
            times = track.times_s[selected]
            weights = np.linalg.solve(_noise_covariance(times, b.scan.config), np.ones(len(times)))
            weights /= weights.sum()
            self.support.append((times, weights, track.frequencies_hz[selected], rx))
            if identity < port.candidate_count:
                for j in eligible:
                    self.contributions[j][k] = self.ratio(j, means[offset])
                    offset += 1
        assert offset == len(means)
        self.group_scores = [self.log_ratio(list(c.values())) for c in self.contributions]
        assert abs(sum(self.group_scores)-self.additional) < 1e-7

    def ratio(self, group, mean):
        b, g = self.base, self.base.groups[group]
        return float(g['period']*np.mean(wrapped_cauchy_pdf(
            g['candidates']-mean, g['period'], b.parameters['scale_hz'])))

    def log_ratio(self, ratios):
        if not ratios:
            return 0.
        p = self.base.parameters['signal_probability']
        return float(np.log((1-p)+p*np.mean(ratios)))

    def score(self, track, identity):
        b = self.base
        port = b.ports[track]
        if not 0 <= identity <= port.candidate_count:
            raise ValueError('identity outside catalogue')
        choices = self.assignments.copy()
        choices[track] = identity
        clean, prior_gain = profile_unused_epochs(self.state, choices, len(self.state)-5)
        # Clutter visibility can depend on unassigned epochs. Recompute all
        # training terms when profiling changes any epoch, rather than assume
        # their independence. Active prediction epochs are unchanged.
        if prior_gain:
            precision = np.r_[0., 0., 1., np.full(len(clean)-3, 4.)]
            training = float(.5*(precision*clean)@clean-sum(p.score_selected(clean, i)
                for p, i in zip(b.ports, choices, strict=True)))
        else:
            training = self.training+self.scores[track]-port.score_selected(clean, identity)
        eligible = self.eligible[track]
        new_means = None
        if identity < port.candidate_count and eligible:
            times, weights, measured, rx = self.support[track]
            query = copy.copy(port.likelihood)
            query.bank = port._row_bank(identity)
            query.times = np.r_[times, [b.groups[j]['time'] for j in eligible]]
            positions, velocities = query._orbit_states_per_satellite([clean[2]+clean[5+identity]])
            line = positions[0]-self.receiver
            line /= np.linalg.norm(line, axis=1, keepdims=True)
            factor = b.scan.config.doppler_sign*b.scan.config.reference_frequency_hz/LIGHT_KM_S
            raw = factor*np.sum(velocities[0]*line, axis=1)
            raw += clean[3+rx]*port.likelihood.drift_scale*(query.times-times.mean())
            new_means = raw[len(times):]+weights@(measured-raw[:len(times)])
        additional = self.additional
        for local, group in enumerate(eligible):
            # Sum retained components directly: subtraction of a dominant
            # component could erase a small remaining component numerically.
            ratios = [v for k, v in self.contributions[group].items() if k != track]
            if new_means is not None:
                ratios.append(self.ratio(group, new_means[local]))
            additional += self.log_ratio(ratios)-self.group_scores[group]
        return training-additional, clean, choices, prior_gain
