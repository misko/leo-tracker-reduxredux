"""Exact signed all-point single-satellite bias profiles, no orbit re-projection."""
import time
import numpy as np

from leo.analysis.regional_position_score import ALIAS_HZ, circular
from model import BIAS_BOUND_HZ


class BiasProfiles:
    def __init__(self, model, vector, nuisance, *, evaluated=None):
        ev, details = model.evaluate_details(vector, nuisance) if evaluated is None else evaluated
        self.model = model
        self.initial_objective = float(ev[0])
        self.fixed_penalty = float(ev[0]-ev[3].nll)
        self.bias = np.asarray(nuisance)[model.bias_start:].copy()
        self.residual = ev[3].residual_hz
        self.sigma = details['sigma_hz']
        p = details['visibility_weight']*details['detection_probability'][None, :]
        self.odds = p/(1-p)
        signal = self.odds*np.exp(-.5*(self.residual/self.sigma[:, None])**2)/(self.sigma[:, None]*np.sqrt(2*np.pi))
        clutter = model.score.clutter_rate/ALIAS_HZ
        total = clutter+signal.sum(axis=1)
        self.remaining = np.maximum(total[:, None]-signal, clutter)
        self.log_normalizer = np.log(model.score.clutter_rate+self.odds.sum(axis=1)).sum()
        self.calls = 0

    def score(self, proposed):
        """Column k substitutes ONLY satellite k's constant bias at every row."""
        proposed = np.asarray(proposed, float)
        if proposed.shape != self.bias.shape or np.any(abs(proposed) > BIAS_BOUND_HZ):
            raise ValueError('One bounded independent satellite bias trial per column required')
        residual = circular(self.residual-(proposed-self.bias)[None, :])
        signal = self.odds*np.exp(-.5*(residual/self.sigma[:, None])**2)/(self.sigma[:, None]*np.sqrt(2*np.pi))
        nll = self.log_normalizer-np.log(self.remaining+signal).sum(axis=0)
        self.calls += 1
        return nll+self.fixed_penalty+.5*(proposed**2-self.bias**2)/self.model.bias_sigma_hz**2

    def search(self, *, deadline=float('inf')):
        best = np.full(len(self.bias), self.initial_objective)
        biases = self.bias.copy()
        for value in np.arange(-BIAS_BOUND_HZ, BIAS_BOUND_HZ+.1, 250.):
            if time.monotonic() >= deadline:
                break
            trial = np.full(len(self.bias), value)
            score = self.score(trial)
            take = score < best
            best[take], biases[take] = score[take], trial[take]
        centers = biases.copy()
        for offset in np.arange(-200., 200.1, 50.):
            if time.monotonic() >= deadline:
                break
            trial = np.clip(centers+offset, -BIAS_BOUND_HZ, BIAS_BOUND_HZ)
            score = self.score(trial)
            take = score < best
            best[take], biases[take] = score[take], trial[take]
        return [dict(index=int(k), satellite=int(self.model.bank.numbers[k]),
            bias_hz=float(biases[k]), objective=float(best[k]),
            gain=float(self.initial_objective-best[k]))
            for k in np.argsort(best, kind='stable') if best[k] < self.initial_objective-.1]


def fit(context, *, max_evaluations=1000, max_seconds=120):
    from common import refit
    begun = time.monotonic()
    deadline = min(begun+max_seconds, context.deadline)
    model = context.model
    v, n = context.vector.copy(), context.nuisance.copy()
    actual = surrogate = 0
    rounds = []
    current = float('inf')
    for iteration in range(2):
        if actual >= max_evaluations*.2 or time.monotonic() >= begun+.4*max_seconds:
            break
        evaluated = model.evaluate_details(v, n)
        actual += 1
        profile = BiasProfiles(model, v, n, evaluated=evaluated)
        current = profile.initial_objective
        proposals = profile.search(deadline=min(deadline, begun+.4*max_seconds))
        surrogate += profile.calls
        trials = []
        for proposal in proposals[:20]:
            if actual >= max_evaluations*.2 or time.monotonic() >= begun+.5*max_seconds:
                break
            nn = n.copy()
            nn[model.bias_start+proposal['index']] = proposal['bias_hz']
            ev = model.evaluate_details(v, nn)
            actual += 1
            accepted = ev[0][0] < current-1e-7
            trials.append(dict(proposal=proposal, actual_objective=float(ev[0][0]), accepted=accepted))
            if accepted:
                n, current = nn, float(ev[0][0])
        rounds.append(dict(initial_objective=profile.initial_objective,
            proposals=proposals, trials=trials))
    remaining = max_evaluations-actual
    polish = {}
    if remaining > 0 and time.monotonic() < deadline:
        solved = refit(context, v, n, max_evaluations=remaining,
            max_seconds=deadline-time.monotonic(), fixed_c=context.fixed_c)
        polish = solved['diagnostics']
        actual += polish['evaluations']
        if polish['objective'] <= current+1e-7:
            v, n, current = solved['vector'], solved['nuisance'], polish['objective']
    return dict(vector=v, nuisance=n, diagnostics=dict(method='signed-all-point-constant-bias-profiles',
        sigma_bias_hz=model.bias_sigma_hz, evaluations=actual, surrogate_profile_calls=surrogate,
        orbit_proposal_projections=0, rounds=rounds, objective=float(current), polish=polish,
        elapsed_seconds=float(time.monotonic()-begun),
        qualification='Empirical constant-Hz satellite nuisance, not an identified hardware/orbit error; original point classifier and q normalization.'))
