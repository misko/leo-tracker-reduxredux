"""Retain the first numerically equivalent proposal before Graph arbitration."""

from collections import defaultdict
from contextlib import contextmanager
from time import process_time_ns
from unittest.mock import patch

import numpy as np


def equivalent(a, b, observed, alias_period, gate):
    from leo.analysis.polynomial_tracklets import _wrap

    if np.max(np.abs(a-b)) > np.spacing(alias_period):
        return False
    da, db = observed-a, observed-b
    if not np.array_equal(np.rint(da/alias_period), np.rint(db/alias_period)):
        return False
    ra = np.abs(_wrap(da, alias_period))
    rb = np.abs(_wrap(db, alias_period))
    return np.array_equal(ra < gate, rb < gate)


def unique_proposals(times, values, models, config):
    from leo.analysis.polynomial_tracklets import _predict

    kept, by_support = [], defaultdict(list)
    alias_period = config.alias_spacing_hz
    gate = config.association_sigma * config.noise_sigma_hz
    for model in models:
        indices = model["indices"]
        if not len(indices):
            kept.append(model)
            continue
        key = (indices.dtype.str, indices.tobytes(), model["degree"], model["reference_time_s"], model["time_scale_s"])
        peers = by_support[key]
        if peers:
            at, observed = times[indices], values[indices]
            current = _predict(model, at)
            if np.isfinite(current).all() and any(
                equivalent(current, _predict(prior, at), observed, alias_period, gate) for prior in peers
            ):
                continue
        peers.append(model)
        kept.append(model)
    return kept


@contextmanager
def stable_finalization(audit):
    from leo.analysis import graph_tracklets

    original = graph_tracklets.finish_lane

    def finish(t, y, order, n, models, config, **kwargs):
        started = process_time_ns()
        retained = unique_proposals(t, y, models, config)
        audit["calls"] += 1
        audit["skipped"] += len(models) - len(retained)
        audit["cpu_ns"] += process_time_ns() - started
        return original(t, y, order, n, retained, config, **kwargs)

    with patch.object(graph_tracklets, "finish_lane", finish):
        yield
