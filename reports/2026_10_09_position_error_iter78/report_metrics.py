"""Explicit denominators and paired errors; never impute missing outcomes."""

import numpy as np


def distribution(values):
    data = np.asarray(values, dtype=float)
    if not np.isfinite(data).all():
        raise ValueError("Nonfinite result is an explicit failure, not a valid metric")
    if not len(data):
        return dict(n=0, mean=None, median=None, p95=None, worst=None)
    return dict(
        n=len(data),
        mean=float(data.mean()),
        median=float(np.median(data)),
        p95=float(np.percentile(data, 95)),
        worst=float(data.max()),
    )


def paired(candidate, comparator):
    if len(candidate) != len(comparator):
        raise ValueError("Paired comparison requires identical membership")
    delta = np.asarray(candidate) - np.asarray(comparator)
    return dict(
        n=len(delta),
        improved=int(sum(delta < -0.001)),
        regressed=int(sum(delta > 0.001)),
        tied=int(sum(abs(delta) <= 0.001)),
    )
