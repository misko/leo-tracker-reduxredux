"""Conditional same-candidate evidence for disjoint observed track groups.

The independent-window score remains the reference branch. The shared branch
averages over one catalogue identity for the group and retains a per-window
clutter alternative. A fixed mixture lets incompatible groups revert to the
independent branch rather than forcing a wrong identity or dropping windows.
This experimental mark correlation retains the original singleton count terms;
it is not a new physical model of correlated transmission/detection counts.
"""

from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import WindowLikelihood


@dataclass(frozen=True)
class SharedGroupEvidence:
    rows: tuple[int, ...]
    log_bayes_factor: float
    posterior_shared: float
    identity_probabilities: np.ndarray


def shared_track_likelihood(measured, prediction, visible, score, groups, *, shared_prior=0.5):
    return shared_track_terms(
        likelihood(measured, prediction, visible, score), groups, shared_prior=shared_prior
    )


def shared_track_terms(base: WindowLikelihood, groups, *, shared_prior=0.5):
    """Return singleton-compatible terms and conditional group evidence.

    If H_n = C + sum_k S_nk, the shared/independent mark-density ratio is
        B_g = (1/K) sum_k product_{n in g} (C + K S_nk) / H_n.
    The final ratio is (1-p) + p B_g. One-row groups and p=0 reproduce the
    original score exactly. No duplicate row is allowed, including across groups.
    """
    if not np.isfinite(shared_prior) or not 0 <= shared_prior <= 1:
        raise ValueError("shared prior must lie in [0, 1]")
    n, count = base.responsibilities.shape
    used, checked = set(), []
    for group in groups:
        rows = np.asarray(group)
        if (
            rows.ndim != 1
            or len(rows) == 0
            or not np.issubdtype(rows.dtype, np.integer)
            or np.any(rows < 0)
            or np.any(rows >= n)
            or len(np.unique(rows)) != len(rows)
            or used.intersection(rows.tolist())
        ):
            raise ValueError("track groups must contain unique disjoint valid row indices")
        used.update(rows.tolist())
        checked.append(rows.astype(int))
    if shared_prior == 0 or not checked:
        return base, ()
    if not np.isfinite(base.nll) or np.any(base.clutter_probability <= 0):
        raise ValueError("shared track model requires a finite positive clutter floor")
    responsibilities = base.responsibilities.copy()
    clutter = base.clutter_probability.copy()
    gradient = base.prediction_gradient.copy()
    nll, evidence = base.nll, []
    for rows in checked:
        if len(rows) == 1:
            # Analytic singleton closure; avoid introducing roundoff differences.
            evidence.append(
                SharedGroupEvidence(
                    tuple(rows),
                    0.0,
                    shared_prior,
                    base.clutter_probability[rows[0]] / count + base.responsibilities[rows[0]],
                )
            )
            continue
        original = base.responsibilities[rows]
        conditional = base.clutter_probability[rows, None] + count * original
        log_products = np.log(conditional).sum(axis=0)
        log_sum = logsumexp(log_products)
        log_factor = float(log_sum - np.log(count))
        log_shared = np.log(shared_prior) + log_factor
        log_mixed = np.logaddexp(
            -np.inf if shared_prior == 1 else np.log1p(-shared_prior), log_shared
        )
        posterior_shared = float(np.exp(log_shared - log_mixed))
        identity = np.exp(log_products - log_sum)
        shared_responsibility = identity[None, :] * count * original / conditional
        updated = (1 - posterior_shared) * original + posterior_shared * shared_responsibility
        responsibilities[rows] = updated
        clutter[rows] = np.clip(1 - updated.sum(axis=1), 0, 1)
        derivative = np.divide(
            base.prediction_gradient[rows],
            original,
            out=np.zeros_like(original),
            where=original > 0,
        )
        gradient[rows] = derivative * updated
        nll -= float(log_mixed)
        evidence.append(SharedGroupEvidence(tuple(rows), log_factor, posterior_shared, identity))
    return WindowLikelihood(nll, responsibilities, clutter, gradient, base.residual_hz), tuple(
        evidence
    )
