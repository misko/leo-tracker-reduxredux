"""Exact assignment partition: each satellite owns any subset, each track once.

Factors enumerate subsets of tracks that can name one physical satellite. The
global dynamic program stores only the set of already assigned tracks, rather
than enumerating every catalogue assignment. No candidate pruning is used.
"""
import numpy as np


def partition(n_tracks, factors, max_tracks=16):
    if not 0 <= n_tracks <= max_tracks:
        raise ValueError('exact source-assignment state budget exceeded')
    dimensions = factors[0][2].shape[-1] if factors else 0
    states = np.arange(1 << n_tracks, dtype=np.int64)
    score = np.full(len(states), -np.inf)
    score[0] = 0.
    gradient = np.zeros((len(states), dimensions))
    for tracks, values, derivatives in factors:
        tracks = list(tracks)
        values = np.asarray(values, float)
        derivatives = np.asarray(derivatives, float)
        if len(set(tracks)) != len(tracks) or any(t < 0 or t >= n_tracks for t in tracks):
            raise ValueError('invalid source track support')
        if values.shape != (1 << len(tracks),) or derivatives.shape != (len(values), dimensions):
            raise ValueError('invalid source subset table')
        if values[0] != 0. or np.any(derivatives[0] != 0.) or np.isnan(values).any() or np.isposinf(values).any() or not np.isfinite(derivatives).all():
            raise ValueError('empty source must have unit weight; invalid factors')
        new_score, new_gradient = score.copy(), gradient.copy()
        for subset in range(1, len(values)):
            if not np.isfinite(values[subset]):
                continue
            mask = sum(1 << t for j, t in enumerate(tracks) if subset & (1 << j))
            previous = states[((states & mask) == 0) & np.isfinite(score)]
            if not len(previous):
                continue
            target = previous | mask
            candidate = score[previous] + values[subset]
            combined = np.logaddexp(new_score[target], candidate)
            weight = np.exp(candidate - combined)
            new_gradient[target] = (1 - weight[:, None]) * new_gradient[target] + weight[:, None] * (gradient[previous] + derivatives[subset])
            new_score[target] = combined
        score, gradient = new_score, new_gradient
    return float(score[-1]), gradient[-1]
