"""Normalized refresh-state filter with analytic sensitivities."""
import numpy as np


def sequence_score(times, log_probabilities, states, observed, tau_s, derivatives=None, log_tau_axis=None):
    times = np.asarray(times, float)
    logp = np.asarray(log_probabilities, float)
    states = np.asarray(states, int)
    observed = np.asarray(observed, bool)
    if logp.ndim != 3 or logp.shape[1:] != (len(times), 3) or states.shape != times.shape or observed.shape != times.shape:
        raise ValueError('expected C,N,3 probabilities and N observation design')
    if not np.isfinite(times).all() or (np.diff(times) < 0).any() or not np.isfinite(logp).all() or not np.isin(states[observed], [1, 2, 3]).all():
        raise ValueError('invalid times, probabilities or observed states')
    if not np.isfinite(tau_s) or tau_s < 0:
        raise ValueError('invalid correlation timescale')
    prob = np.exp(logp)
    if not np.allclose(prob.sum(axis=-1), 1., atol=1e-10):
        raise ValueError('receiver distributions must normalize')
    if derivatives is None:
        derivatives = np.zeros(logp.shape + (0,))
    derivatives = np.asarray(derivatives, float)
    if derivatives.shape[:-1] != logp.shape:
        raise ValueError('derivative shape mismatch')
    dimensions = derivatives.shape[-1]
    if log_tau_axis is not None and not 0 <= log_tau_axis < dimensions:
        raise ValueError('invalid timescale derivative axis')
    dprob = prob[..., None] * derivatives
    score = np.zeros(len(logp))
    grad = np.zeros((len(logp), dimensions))
    if not len(times):
        return score, grad
    alpha = prob[:, 0].copy()
    da = dprob[:, 0].copy()
    for i in range(len(times)):
        if i:
            dt = times[i] - times[i - 1]
            rho = np.exp(-dt / tau_s) if tau_s else 0.
            new_da = rho * da + (1 - rho) * dprob[:, i]
            if log_tau_axis is not None and tau_s:
                new_da[..., log_tau_axis] += rho * dt / tau_s * (alpha - prob[:, i])
            alpha = rho * alpha + (1 - rho) * prob[:, i]
            da = new_da
        if observed[i]:
            state = states[i] - 1
            value = alpha[:, state]
            if (value <= 0).any():
                raise ValueError('observed transition has no support')
            score += np.log(value)
            grad += da[:, state] / value[:, None]
            alpha = np.zeros_like(alpha)
            alpha[:, state] = 1.
            da = np.zeros_like(da)
    return score, grad
