"""Training-evidence averaging of acquisition, broad-frequency and null models."""

import numpy as np
from ds789_frequency_mixture import logsumexp


def posterior(log_evidence, prior):
    evidence = np.asarray(log_evidence, dtype=float)
    prior = np.asarray(prior, dtype=float)
    if evidence.ndim != 1 or evidence.shape != prior.shape or not len(prior):
        raise ValueError("component dimensions disagree")
    if not np.all(np.isfinite(evidence)) or not np.all(np.isfinite(prior)) or np.any(prior <= 0):
        raise ValueError("finite evidence and positive priors required")
    if not np.isclose(prior.sum(), 1, atol=1e-12, rtol=0):
        raise ValueError("prior must sum to one")
    joint = evidence + np.log(prior)
    return joint - logsumexp(joint)


def predictive_ratio(log_weights, component_log_ratios):
    weights = np.asarray(log_weights, dtype=float)
    ratios = np.asarray(component_log_ratios, dtype=float)
    if weights.shape != ratios.shape or weights.ndim != 1:
        raise ValueError("component dimensions disagree")
    if not np.all(np.isfinite(weights)) or not np.all(np.isfinite(ratios)):
        raise ValueError("finite weights and predictions required")
    if abs(logsumexp(weights)) > 1e-10:
        raise ValueError("posterior weights must be normalized")
    return logsumexp(weights + ratios)
