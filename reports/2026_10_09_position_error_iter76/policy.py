"""Candidate extra-search flags from fitted quantities only; never abstention."""

import numpy as np


def timing_metric(fit):
    if fit is None:
        return dict(available=False, converged=False, normalized_energy=None)
    v = np.asarray(fit["vector"], dtype=float)
    if v.ndim != 1 or len(v) <= 8 or not np.isfinite(v).all():
        raise ValueError("invalid joint-fit vector")
    return dict(
        available=True,
        converged=bool(fit["converged"]),
        normalized_energy=float(np.mean(v[8:] ** 2) / 2**2),
        relative_dimensions=len(v) - 8,
    )


def trigger(metrics, threshold):
    """Use the union across arms so proposed extra budgets stay matched."""
    return any(
        not r["available"] or not r["converged"] or r["normalized_energy"] > threshold
        for r in metrics.values()
    )
