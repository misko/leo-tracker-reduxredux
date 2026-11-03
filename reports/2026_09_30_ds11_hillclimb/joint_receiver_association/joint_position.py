"""Conditional receiver/Doppler joint matching position objective."""
import numpy as np
from scipy.special import logsumexp
from doppler_pilot import fast
from matching import evidence


def mixture(values, derivatives, catalogue_size):
    normal = logsumexp(values)
    if not np.isfinite(normal):
        return -np.inf, np.zeros(3)
    return float(normal - np.log(catalogue_size)), np.exp(values - normal) @ derivatives


class JointPosition:
    def __init__(self, doc, config, bound, calibration, arm):
        self.geometry = fast.Stationary(doc, config)
        self.tracks = {t['track_id']: t for t in doc['tracks']}
        self.meta = {t['track_id']: t for t in bound['tracks']}
        self.lanes = bound['lanes']
        self.arm = arm
        self.calibration = calibration
        self.permutations = {}
        rng = np.random.default_rng(20260930)
        for tid in sorted(self.tracks):
            self.permutations[tid] = rng.permutation(len(self.meta[tid]['candidate_norad']))
        for opportunity in bound['opportunities']:
            assert all(opportunity['receivers'][r]['receiver_status'].startswith('observed_') for r in ('rx0', 'rx1'))

    def receiver_probabilities(self, track, tid, x):
        """C,N,3 conditional log probabilities on original bank support."""
        c, _, n, _ = track['candidate_position_km'].shape
        if self.arm == 'doppler':
            return np.zeros((c, n, 3))
        key = 'receiver' if self.arm == 'receiver' else 'signed'
        p = np.array(self.calibration['arms'][key]['selected']['parameters'])
        rf = self.calibration['frequencies'].index(self.meta[tid]['rf_hz'])
        eta = np.broadcast_to(p[2 * rf:2 * rf + 2], (c, n, 2)).copy()
        if self.arm != 'receiver':
            lat, lon = self.geometry.coordinates(x)
            rec, up = fast.baseline.site(lat, lon)
            tau = self.geometry.taus
            hi = min(max(int(np.searchsorted(tau, x[2], side='right')), 1), len(tau) - 1)
            lo = hi - 1
            w = (x[2] - tau[lo]) / (tau[hi] - tau[lo])
            positions = track['candidate_position_km'][:, lo] * (1 - w) + track['candidate_position_km'][:, hi] * w
            unit = positions - rec
            unit /= np.linalg.norm(unit, axis=-1)[..., None]
            if self.arm == 'permuted':
                unit = unit[self.permutations[tid]]
            east = np.array([-np.sin(np.radians(lon)), np.cos(np.radians(lon)), 0.])
            sign = np.array([-1., 1.]) * (-1 if self.arm == 'swapped' else 1)
            eta += p[-1] * (np.cos(np.radians(10.)) * (unit @ up)[..., None] + np.sin(np.radians(10.)) * (unit @ east)[..., None] * sign)
        weights = np.stack((eta[..., 0], eta[..., 1], eta.sum(axis=-1)), axis=-1)
        return weights - logsumexp(weights, axis=-1)[..., None]

    def evaluate(self, x, gradient=True, held=False):
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
                    windows = {}
                    for tid in tids:
                        for i in np.flatnonzero(keeps[tid]):
                            if held or self.tracks[tid]['mask'][i]:
                                windows.setdefault(self.meta[tid]['window_ids'][i], []).append((tid, i))
                    for entries in windows.values():
                        # Repeated points within one receiver/window do not create new RX evidence.
                        state = sum(1 << r for r in {int(self.meta[t]['receiver']) for t, i in entries})
                        tid, i = entries[0]
                        values = values + base[tid][2][indices[tid], i, state - 1]
                        derivative = derivative + base[tid][4][indices[tid], i, state - 1]
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
            score = logsumexp([b[0] for b in branches])
            weights = np.exp([b[0] - score for b in branches])
            grad = sum(w * b[1] for w, b in zip(weights, branches))
            pairs = sum(w * b[2] for w, b in zip(weights, branches))
            lane_results.append(dict(score=float(score), gradient=grad, expected_pairs=float(pairs.sum()), pair_posterior=pairs.tolist(), ownership_posterior=weights.tolist()))
        return dict(score=sum(r['score'] for r in lane_results), gradient=sum((r['gradient'] for r in lane_results), start=np.zeros(3)), expected_pairs=sum(r['expected_pairs'] for r in lane_results), lanes=lane_results)
