"""Joint identity evidence for disjoint epoch-matched receiver observations.

The single-detection/clutter terms and total double-signal prior mass are
preserved. Conditional on two real signals, rho shares a satellite identity;
the remaining probability retains independent identities. No extra observations
or paired residual penalty are added. Pair admission is orbit/frequency blind.
"""
import numpy as np
from scipy.special import logsumexp

from leo.analysis.regional_position_score import (
    ALIAS_HZ, PositionObjective, WindowLikelihood, circular, predict_orbits,
    singleton_likelihood,
)


def validate_pairs(pairs, count):
    pairs = np.asarray(pairs, dtype=int).reshape(-1, 2)
    if np.any(pairs < 0) or np.any(pairs >= count):
        raise ValueError("pair index outside observations")
    if len(np.unique(pairs)) != pairs.size:
        raise ValueError("paired observations must be disjoint")
    return pairs


def coupled_likelihood(measured, prediction, visible, score, pairs, rho):
    if not 0 <= rho <= 1:
        raise ValueError("invalid shared-identity probability")
    pairs = validate_pairs(pairs, len(measured))
    original = singleton_likelihood(measured, prediction, visible, score)
    if rho == 0 or not len(pairs):
        return original
    q = np.where(visible, score.detection_budget / prediction.shape[1], 0.)
    log_odds = np.full_like(q, -np.inf)
    log_odds[visible] = np.log(q[visible]) - np.log1p(-q[visible])
    residual = circular(np.asarray(measured)[:, None] - prediction)
    sigma = score.sigma_hz
    count = max(1, int(np.ceil((sigma*np.sqrt(-2*np.log(1e-15)) + ALIAS_HZ/2) / ALIAS_HZ)))
    images = residual[..., None] + np.arange(-count, count+1)*ALIAS_HZ
    log_images = -.5*(images/sigma)**2 - np.log(sigma*np.sqrt(2*np.pi))
    phi = logsumexp(log_images, axis=2)
    mean_image = np.sum(np.exp(log_images-phi[..., None])*images, axis=2)
    signals = log_odds + phi
    log_signal_sum = logsumexp(signals, axis=1)
    log_prior_sum = logsumexp(log_odds, axis=1)
    clutter = np.log(score.clutter_rate / ALIAS_HZ)
    single_h = np.logaddexp(clutter, log_signal_sum)
    responsibility = original.responsibilities.copy()
    clutter_probability = original.clutter_probability.copy()
    nll = original.nll
    log_shared = np.log(rho)
    log_independent = np.log1p(-rho) if rho < 1 else -np.inf
    left, right = pairs.T
    overlap = logsumexp(log_odds[left] + log_odds[right], axis=1)
    # No common visible hypothesis: retain the independent row model.
    valid = np.isfinite(overlap)
    i, j, overlap = left[valid], right[valid], overlap[valid]
    log_boost = log_prior_sum[i] + log_prior_sum[j] - overlap
    log_single_or_clutter = logsumexp(np.stack([
        np.full(len(i), 2*clutter), clutter+log_signal_sum[i],
        clutter+log_signal_sum[j]]), axis=0)
    log_double = np.logaddexp(
        log_independent+log_signal_sum[i]+log_signal_sum[j],
        log_shared+log_boost+logsumexp(signals[i]+signals[j], axis=1),
    )
    pair_h = np.logaddexp(log_single_or_clutter, log_double)
    nll -= float(np.sum(pair_h-single_h[i]-single_h[j]))
    for row, peer in ((i, j), (j, i)):
        companion = np.logaddexp(clutter, np.logaddexp(
            log_independent+log_signal_sum[peer, None],
            log_shared+log_boost[:, None]+signals[peer],
        ))
        responsibility[row] = np.exp(signals[row]+companion-pair_h[:, None])
        clutter_probability[row] = np.exp(clutter+single_h[peer]-pair_h)
    return WindowLikelihood(float(nll), responsibility, clutter_probability,
                            -responsibility*mean_image/sigma**2, residual)


class PairedObjective(PositionObjective):
    def __init__(self, *args, pairs, rho=.9, **kwargs):
        super().__init__(*args, **kwargs)
        self.pairs = validate_pairs(pairs, len(self.observations.window_ids))
        if not 0 <= rho <= 1:
            raise ValueError("invalid shared-identity probability")
        self.rho = rho
        for i, j in self.pairs:
            if (self.observations.receiver[i] == self.observations.receiver[j]
                    or self.observations.rf_hz[i] != self.observations.rf_hz[j]):
                raise ValueError("pairs require distinct receivers on identical RF")
        if self.score.relative_sigma_s != 1:
            raise ValueError("relative timing sigma must remain 1 second")

    def evaluate(self, vector):
        if self.rho == 0:
            return super().evaluate(vector)
        vector = np.asarray(vector, float)
        relative = self.basis @ vector[8:]
        shifts = vector[7] + relative
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], shifts)
        prediction += (self.design @ vector[2:7] + self.baseline)[:, None]
        terms = coupled_likelihood(self.observations.measured_hz, prediction, visible,
                                   self.score, self.pairs, self.rho)
        weight = terms.prediction_gradient
        shift_gradient = np.sum(weight*timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift_gradient.sum() + vector[7]/self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift_gradient + relative/self.score.relative_sigma_s**2)
        penalty = .5*(vector[7]/self.score.common_sigma_s)**2 + .5*np.sum((relative/self.score.relative_sigma_s)**2)
        return terms.nll + float(penalty), gradient, terms
