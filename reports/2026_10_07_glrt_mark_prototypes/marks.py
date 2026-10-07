"""Bounded GLRT marks and exact singleton finite-set likelihood.

Research only: margin ranks are assumed reliability marks, not calibrated
probabilities. One row per source window is required. No satellite truth is used.
"""
import numpy as np
from scipy.special import logsumexp
from scipy.stats import rankdata


def lane_marks(margin, receiver, channel, *, shuffle=False, seed=7007):
    margin = np.asarray(margin, float)
    receiver, channel = np.asarray(receiver), np.asarray(channel)
    if (margin.ndim != 1 or receiver.shape != margin.shape or
            channel.shape != margin.shape or not np.all(np.isfinite(margin))):
        raise ValueError('Finite, aligned margin and lane vectors required')
    marks = np.zeros_like(margin)
    rng = np.random.default_rng(seed)
    for rx, ch in sorted(set(zip(receiver.tolist(), channel.tolist()))):
        rows = np.flatnonzero((receiver == rx) & (channel == ch))
        # Midranks make tied scores identical and a constant lane neutral.
        values = 2*((rankdata(margin[rows], method='average')-.5)/len(rows)-.5)
        if shuffle:
            values = rng.permutation(values)
        marks[rows] = values
    return marks


def mark_settings(marks, mode):
    marks = np.asarray(marks, float)
    if np.any(~np.isfinite(marks)) or np.any(abs(marks) > 1):
        raise ValueError('Marks must be finite and in [-1,1]')
    if mode not in ('control', 'signal-prior', 'precision', 'joint', 'shuffled-joint'):
        raise ValueError('Unknown mark mode')
    prior = mode in ('signal-prior', 'joint', 'shuffled-joint')
    precision = mode in ('precision', 'joint', 'shuffled-joint')
    return np.exp2(marks if prior else np.zeros_like(marks)), np.exp2(
        -.5*marks if precision else np.zeros_like(marks))


class SingletonMarkedLikelihood:
    """Poisson clutter + Bernoulli satellites, conditioned on nonempty.

    Signal odds multiplier is shared by every satellite in a window. Precision
    multiplies the frequency width. Neutral marks reproduce the existing
    finite-set likelihood exactly, including the nonempty count normalizer.
    """
    def __init__(self, measured, group, features, probability, clutter_rate,
                 alias_hz, odds_multiplier, sigma_multiplier):
        self.measured = np.asarray(measured, float)
        self.group = np.asarray(group)
        self.features = np.asarray(features, float)
        self.detection_probability = float(probability)
        self.clutter_rate = float(clutter_rate)
        self.alias_hz = float(alias_hz)
        self.odds_multiplier = np.asarray(odds_multiplier, float)
        self.sigma_multiplier = np.asarray(sigma_multiplier, float)
        n = len(self.measured)
        if (self.measured.ndim != 1 or self.group.shape != (n,) or
                len(np.unique(self.group)) != n or self.features.ndim != 2 or
                self.features.shape[0] != n or self.odds_multiplier.shape != (n,) or
                self.sigma_multiplier.shape != (n,) or
                not 0 < probability < 1 or clutter_rate <= 0 or alias_hz <= 0 or
                not all(np.all(np.isfinite(x)) for x in (self.measured, self.features,
                    self.odds_multiplier, self.sigma_multiplier)) or
                np.any(self.odds_multiplier <= 0) or np.any(self.sigma_multiplier <= 0)):
            raise ValueError('Invalid singleton likelihood inputs')
        self.coefficients = np.zeros(self.features.shape[1])
        self.last_result = None

    def evaluate(self, predicted, visible, *, sigma_hz, return_gradient=False,
                 return_precision=False):
        predicted, visible = np.asarray(predicted, float), np.asarray(visible, bool)
        if (predicted.ndim != 2 or predicted.shape != visible.shape or
                predicted.shape[0] != len(self.measured) or predicted.shape[1] < 1 or
                not np.all(np.isfinite(predicted)) or not np.isfinite(sigma_hz) or sigma_hz <= 0):
            raise ValueError('Invalid prediction bank or frequency width')
        predicted = predicted+(self.features@self.coefficients)[:, None]
        residual = (self.measured[:, None]-predicted+self.alias_hz/2)%self.alias_hz-self.alias_hz/2
        sigma = sigma_hz*self.sigma_multiplier[:, None]
        count = max(1, int(np.ceil((float(sigma.max())*np.sqrt(-2*np.log(1e-15))+
                                   self.alias_hz/2)/self.alias_hz)))
        shifted = residual[:, :, None]+np.arange(-count, count+1)*self.alias_hz
        images = -.5*(shifted/sigma[:, :, None])**2-np.log(sigma[:, :, None])-.5*np.log(2*np.pi)
        density = logsumexp(images, axis=2)
        image_gradient = np.sum(np.exp(images-density[:, :, None])*shifted, axis=2)/sigma**2
        odds = self.detection_probability/(1-self.detection_probability)*self.odds_multiplier[:, None]
        log_miss = -np.log1p(odds)*visible
        prefix = -self.clutter_rate+log_miss.sum(axis=1)
        signal = np.where(visible, np.log(odds)+density, -np.inf)
        terms = np.column_stack((np.full(len(predicted), np.log(self.clutter_rate/self.alias_hz)), signal))
        denominator = logsumexp(terms, axis=1)
        # Probability of a nonempty set under these per-window detection odds.
        log_nonempty = np.log(-np.expm1(prefix))
        log_likelihood = prefix+denominator-log_nonempty
        posterior = np.exp(signal-denominator[:, None])
        result = dict(total_log_likelihood=float(log_likelihood.sum()),
            log_likelihood=log_likelihood, row_association_probability=posterior,
            prediction_gradient=posterior*image_gradient,
            prediction_precision=posterior/sigma**2,
            clutter_probability=1-posterior.sum(axis=1),
            satellite_support=posterior.sum(axis=0), sigma_hz=sigma_hz,
            alias_hz=self.alias_hz)
        self.last_result = result
        return result
