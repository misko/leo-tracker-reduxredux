"""Exact whole-source assignment with correlated conditional receiver states."""
import numpy as np
from scipy.special import logsumexp
from joint_position import JointPosition
from source_partition_fast import partition
from doppler_pilot import fast
from batched_filter import filter_subsets


class TemporalWholeSourcePosition(JointPosition):
    def __init__(self, doc, config, bound, calibration, arm, tau_s):
        super().__init__(doc, config, bound, calibration, arm)
        self.tau_s = tau_s
        anchor = min(o['window_start_utc_ns'] for o in bound['opportunities'])
        self.window_times = {o['source_window_id']: ((o['window_start_utc_ns'] - anchor) + (o['window_end_utc_ns'] - anchor)) / 2e9 for o in bound['opportunities']}

    def evaluate(self, x, gradient=True, held=False, force_partition=False):
        if gradient and held:
            raise ValueError('held profile gradient is not a training envelope')
        x = np.asarray(x, float)
        dimensions = 4 if gradient else 1
        base = {}
        for tid, track in self.tracks.items():
            pred, visible = self.geometry.prediction(track, x)
            rx = self.receiver_probabilities(track, tid, x)
            dp = np.zeros(pred.shape + (dimensions,))
            dr = np.zeros(rx.shape + (dimensions,))
            if gradient:
                for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
                    plus, minus = x.copy(), x.copy()
                    plus[axis] += step
                    minus[axis] -= step
                    if axis == 2:
                        plus[axis], minus[axis] = min(5., plus[axis]), max(-5., minus[axis])
                    width = plus[axis] - minus[axis]
                    dp[..., axis] = (self.geometry.prediction(track, plus)[0] - self.geometry.prediction(track, minus)[0]) / width
                    dr[..., axis] = (self.receiver_probabilities(track, tid, plus) - self.receiver_probabilities(track, tid, minus)) / width
            base[tid] = (track['y'][None, :] - pred, visible, rx, dp, dr)
        profiles, results = {}, []
        for lane in self.lanes:
            tids = sorted(lane['left'] + lane['right'])
            if len(tids) > 16:
                raise ValueError('whole-source exact assignment budget exceeded')
            branches = []
            for branch in lane['ownership_alternatives']:
                scores, derivatives, keeps = {}, {}, {}
                for tid in tids:
                    track, meta = self.tracks[tid], self.meta[tid]
                    keep = np.array([branch['assignment'].get(c, tid) == tid for c in meta['candidate_ids']])
                    keeps[tid] = keep
                    key = tid, tuple(np.flatnonzero(~keep))
                    if key not in profiles:
                        residual, visible, rx, dp, dr = base[tid]
                        mask = track['mask'][keep]
                        if mask.sum() < 2:
                            raise ValueError('insufficient owned training support')
                        train, joint, audits, offsets = fast.profile(residual[:, keep], mask)
                        assert all(a['converged'] for a in audits)
                        centered = residual[:, keep][:, mask] - offsets[:, None]
                        slope = 5 * centered / (40000 + centered**2)
                        deriv = np.einsum('cn,cna->ca', slope, dp[:, keep][:, mask])
                        profiles[key] = (np.where(visible, joint if held else train, -np.inf) - np.log(track['catalogue_size']), deriv)
                    scores[tid], derivatives[tid] = profiles[key]
                candidates = sorted({c for t in tids for c in self.meta[t]['candidate_norad']})
                if self.arm == 'doppler' and not force_partition:
                    value = sum(logsumexp(scores[t]) for t in tids)
                    deriv = sum((np.exp(scores[t] - logsumexp(scores[t])) @ derivatives[t] for t in tids), start=np.zeros(dimensions))
                    presence = 0.
                    for candidate in candidates:
                        absent = 1.
                        for tid in tids:
                            ids = self.meta[tid]['candidate_norad']
                            if candidate in ids:
                                absent *= 1 - np.exp(scores[tid][ids.index(candidate)] - logsumexp(scores[tid]))
                        presence += 1 - absent
                    deriv[-1] = presence
                else:
                    factors = []
                    for candidate in candidates:
                        support = [i for i, t in enumerate(tids) if candidate in self.meta[t]['candidate_norad']]
                        k = len(support)
                        selected_tids = [tids[i] for i in support]
                        indices = {t: self.meta[t]['candidate_norad'].index(candidate) for t in selected_tids}
                        subsets = np.arange(1 << k, dtype=np.int64)
                        bits = (subsets[:, None] >> np.arange(k)) & 1
                        node_values = np.array([scores[t][indices[t]] for t in selected_tids])
                        finite = np.isfinite(node_values)
                        values = bits @ np.where(finite, node_values, 0.)
                        grad = bits @ np.array([derivatives[t][indices[t]] for t in selected_tids])
                        if self.arm != 'doppler':
                            observations = []
                            windows = set()
                            for tid in selected_tids:
                                active = keeps[tid]
                                points = {}
                                for i in np.flatnonzero(active):
                                    points.setdefault(self.meta[tid]['window_ids'][i], int(i))
                                observations.append(points)
                                windows.update(points)
                            windows = sorted(windows, key=lambda w: (self.window_times[w], w))
                            window_index = {w: i for i, w in enumerate(windows)}
                            masks = np.zeros((2, len(windows)), dtype=np.int64)
                            logp = np.zeros((k, len(windows), 3))
                            dlog = np.zeros(logp.shape + (dimensions,))
                            training = np.full(len(windows), -1, dtype=int)
                            for j, (tid, points) in enumerate(zip(selected_tids, observations)):
                                for window, i in points.items():
                                    w = window_index[window]
                                    masks[self.meta[tid]['receiver'], w] |= 1 << j
                                    logp[j, w] = base[tid][2][indices[tid], i]
                                    dlog[j, w] = base[tid][4][indices[tid], i]
                                    split = int(self.tracks[tid]['mask'][i])
                                    assert training[w] in (-1, split)
                                    training[w] = split
                            present = subsets[:, None] & (masks[0] | masks[1])[None, :]
                            first = np.zeros(1 << k, dtype=int)
                            for mask in range(1, len(first)):
                                first[mask] = (mask & -mask).bit_length() - 1
                            owner = first[present]
                            state = ((subsets[:, None] & masks[0]) != 0).astype(int) + 2 * ((subsets[:, None] & masks[1]) != 0)
                            probabilities = logp[owner, np.arange(len(windows))[None, :]]
                            sensitivities = dlog[owner, np.arange(len(windows))[None, :]]
                            rx_value, rx_derivative = filter_subsets(np.array([self.window_times[w] for w in windows]), probabilities, state, np.ones(len(windows), bool) if held else training.astype(bool), self.tau_s, sensitivities)
                            values += rx_value
                            grad += rx_derivative
                        values[np.any(bits[:, ~finite], axis=1)] = -np.inf
                        grad[1:, -1] = 1.  # sensitivity to an unused source-count probe
                        factors.append((support, values, grad))
                    value, deriv = partition(len(tids), factors)
                branches.append((branch['log_prior'] + value, deriv))
            normal = logsumexp([b[0] for b in branches])
            weights = np.exp([b[0] - normal for b in branches])
            derivative = sum(w * b[1] for w, b in zip(weights, branches))
            results.append(dict(score=float(normal), derivative=derivative, ownership_posterior=weights.tolist(), rf_hz=lane['rf_hz']))
        derivative = sum((r['derivative'] for r in results), start=np.zeros(dimensions))
        return dict(score=sum(r['score'] for r in results), gradient=derivative[:3] if gradient else np.zeros(3), expected_sources=float(derivative[-1]), lanes=[dict(rf_hz=r['rf_hz'], score=r['score'], expected_sources=float(r['derivative'][-1]), ownership_posterior=r['ownership_posterior']) for r in results])
