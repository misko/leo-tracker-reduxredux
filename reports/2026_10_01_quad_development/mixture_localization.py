"""Fixed-label physical objective with independent/shared residual mixture."""
import numpy as np
from scale_prediction import log_density
from scale_mixture import mixture, track_weights


class MixtureObjective:
    def __init__(self, ports, labels, groups, precision, initial, mode='mixture'):
        if mode not in ('independent', 'shared', 'mixture'): raise ValueError('unknown mode')
        if not len(ports) == len(labels) == len(groups): raise ValueError('binding length')
        ids = [v for p in ports for v in p.observation_ids]
        if len(ids) != len(set(ids)): raise ValueError('reused evidence')
        self.ports, self.labels, self.groups = tuple(ports), tuple(labels), tuple(groups)
        self.precision = np.asarray(precision); self.mode = mode
        active = {0, 1, *np.flatnonzero(initial).tolist()}
        for p, i in zip(ports, labels):
            if i < p.candidate_count:
                pred = p.predict_selected(initial, i)
                active.update(np.flatnonzero(np.any(pred.jacobian != 0, axis=0)).tolist())
        self.active = np.asarray(sorted(active))

    def evaluate(self, x, derivatives=True):
        value = float(.5*(self.precision*x)@x)
        records = {}; active = self.active
        for p, i, group in zip(self.ports, self.labels, self.groups):
            physical = p.score_selected(x, i)
            if not np.isfinite(physical): raise ValueError('ineligible physical score')
            value -= physical
            if i == p.candidate_count: continue
            pred = p.predict_selected(x, i)
            if not pred.eligible: raise ValueError('ineligible prediction')
            r = p.observation-pred.mean; L = np.linalg.cholesky(pred.covariance)
            y = np.linalg.solve(L, r)
            stat = dict(d=len(y), q=float(y@y), logdet=float(2*np.log(np.diag(L)).sum()))
            stat['logpdf'] = log_density(stat['d'], stat['q'], stat['logdet'])
            if derivatives:
                J = np.linalg.solve(L, pred.jacobian[:, active]); stat.update(g=-J.T@y, H=J.T@J)
            records.setdefault(group, []).append(stat)
        gradient = (self.precision*x)[active].copy() if derivatives else None
        metric = np.diag(self.precision[active]) if derivatives else None
        responsibilities = {}
        for group, rows in records.items():
            independent = sum(r['logpdf'] for r in rows)
            shared = log_density(sum(r['d'] for r in rows), sum(r['q'] for r in rows), sum(r['logdet'] for r in rows))
            if self.mode == 'independent':
                target = independent; weights = np.array([(4+r['d'])/(4+r['q']) for r in rows]); rho = 0.
            elif self.mode == 'shared':
                target = shared; weights = np.full(len(rows), (4+sum(r['d'] for r in rows))/(4+sum(r['q'] for r in rows))); rho = 1.
            else:
                target = mixture(rows); weights, rho = track_weights(rows)
            value += independent-target; responsibilities[str(group)] = rho
            if derivatives:
                for w, row in zip(weights, rows): gradient += w*row['g']; metric += w*row['H']
        return value, gradient, metric, responsibilities
