"""Joint position objective with normalized conditional RX-state sequences."""
import numpy as np
from scipy.special import logsumexp
from joint_position import JointPosition, mixture
from doppler_pilot import fast
from matching import evidence
from temporal_receiver import sequence_score


class SequencePosition(JointPosition):
    def __init__(self, doc, config, bound, calibration, arm, tau_s):
        super().__init__(doc, config, bound, calibration, arm)
        self.tau_s = tau_s
        anchor = min(o['window_start_utc_ns'] for o in bound['opportunities'])
        self.window_times = {o['source_window_id']: ((o['window_start_utc_ns'] - anchor) + (o['window_end_utc_ns'] - anchor)) / 2e9 for o in bound['opportunities']}

    def evaluate(self, x, gradient=True, held=False):
        if held and gradient:
            raise ValueError('held profile derivative is not the training envelope')
        x = np.asarray(x, float)
        base = {}
        for tid, t in self.tracks.items():
            pred, visible = self.geometry.prediction(t, x)
            rx = self.receiver_probabilities(t, tid, x)
            dp = np.zeros(pred.shape + (3,))
            dr = np.zeros(rx.shape + (3,))
            if gradient:
                for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
                    plus, minus = x.copy(), x.copy()
                    plus[axis] += step
                    minus[axis] -= step
                    if axis == 2:
                        plus[axis], minus[axis] = min(5., plus[axis]), max(-5., minus[axis])
                    width = plus[axis] - minus[axis]
                    dp[..., axis] = (self.geometry.prediction(t, plus)[0] - self.geometry.prediction(t, minus)[0]) / width
                    dr[..., axis] = (self.receiver_probabilities(t, tid, plus) - self.receiver_probabilities(t, tid, minus)) / width
            base[tid] = (t['y'][None, :] - pred, visible, rx, dp, dr)
        cache = {}
        lane_results = []
        for lane in self.lanes:
            ls, rs = lane['left'], lane['right']
            allowed = {(e['left'], e['right']) for e in lane['edges']}
            prior = np.array([[0. if (a, b) in allowed else -np.inf for b in rs] for a in ls]).reshape(len(ls), len(rs))
            branches = []
            for branch in lane['ownership_alternatives']:
                tables, derivatives, keeps = {}, {}, {}
                for tid in ls + rs:
                    t, m = self.tracks[tid], self.meta[tid]
                    keep = np.array([branch['assignment'].get(cid, tid) == tid for cid in m['candidate_ids']])
                    keeps[tid] = keep
                    key = tid, tuple(np.flatnonzero(~keep))
                    if key not in cache:
                        residual, visible, rx, dp, dr = base[tid]
                        mask = t['mask'][keep]
                        if mask.sum() < 2:
                            raise ValueError('insufficient training observations after ownership')
                        train, joint, audits, offsets = fast.profile(residual[:, keep], mask)
                        assert all(a['converged'] for a in audits)
                        centered = residual[:, keep][:, mask] - offsets[:, None]
                        slope = 5 * centered / (40000 + centered**2)
                        derivative = np.einsum('cn,cna->ca', slope, dp[:, keep][:, mask])
                        cache[key] = (np.where(visible, joint if held else train, -np.inf), derivative)
                    tables[tid], derivatives[tid] = cache[key]

                def factor(tids):
                    common = sorted(set.intersection(*(set(self.meta[t]['candidate_norad']) for t in tids)))
                    if not common:
                        return -np.inf, np.zeros(3)
                    indices = {t: np.array([self.meta[t]['candidate_norad'].index(c) for c in common]) for t in tids}
                    values = sum(tables[t][indices[t]] for t in tids)
                    derivative = sum(derivatives[t][indices[t]] for t in tids)
                    if self.arm != 'doppler':
                        windows = {}
                        for tid in tids:
                            for i in np.flatnonzero(keeps[tid]):
                                windows.setdefault(self.meta[tid]['window_ids'][i], []).append((tid, i))
                        times, states, masks, probabilities, sensitivities = [], [], [], [], []
                        for window in sorted(windows, key=lambda w: (self.window_times[w], w)):
                            entries = windows[window]
                            state = sum(1 << r for r in {int(self.meta[t]['receiver']) for t, i in entries})
                            mask = {bool(self.tracks[t]['mask'][i]) for t, i in entries}
                            assert len(mask) == 1, 'one observing opportunity must have one split'
                            tid, i = entries[0]
                            times.append(self.window_times[window])
                            states.append(state)
                            masks.append(held or mask.pop())
                            probabilities.append(base[tid][2][indices[tid], i])
                            sensitivities.append(base[tid][4][indices[tid], i])
                        receiver, drx = sequence_score(times, np.stack(probabilities, axis=1), states, masks, self.tau_s, np.stack(sensitivities, axis=1))
                        values = values + receiver
                        derivative = derivative + drx
                    sizes = {self.tracks[t]['catalogue_size'] for t in tids}
                    assert len(sizes) == 1
                    return mixture(values, derivative, sizes.pop())

                singles = {t: factor((t,)) for t in ls + rs}
                pair = np.full((len(ls), len(rs)), -np.inf)
                pair_grad = np.zeros(pair.shape + (3,))
                for i, a in enumerate(ls):
                    for j, b in enumerate(rs):
                        if (a, b) in allowed:
                            pair[i, j], pair_grad[i, j] = factor((a, b))
                out = evidence([singles[t][0] for t in ls], [singles[t][0] for t in rs], pair, prior)
                grad = sum((out['left_unmatched'][i] * singles[t][1] for i, t in enumerate(ls)), start=np.zeros(3))
                grad += sum((out['right_unmatched'][i] * singles[t][1] for i, t in enumerate(rs)), start=np.zeros(3))
                grad += np.einsum('ij,ija->a', out['pair_posterior'], pair_grad)
                branches.append((branch['log_prior'] + out['log_evidence'], grad, out['pair_posterior']))
            normal = logsumexp([b[0] for b in branches])
            weights = np.exp([b[0] - normal for b in branches])
            grad = sum(w * b[1] for w, b in zip(weights, branches))
            pairs = sum(w * b[2] for w, b in zip(weights, branches))
            lane_results.append(dict(score=float(normal), gradient=grad, expected_pairs=float(pairs.sum()), pair_posterior=pairs.tolist(), ownership_posterior=weights.tolist()))
        return dict(score=sum(r['score'] for r in lane_results), gradient=sum((r['gradient'] for r in lane_results), start=np.zeros(3)), expected_pairs=sum(r['expected_pairs'] for r in lane_results), lanes=lane_results)
