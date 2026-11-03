"""Exact source partition with structural reachability pruning, never score pruning."""
import numpy as np


def partition(n_tracks, factors, max_tracks=16):
    if not 0 <= n_tracks <= max_tracks:
        raise ValueError('exact source-assignment state budget exceeded')
    dimensions = factors[0][2].shape[-1] if factors else 0
    checked = []
    adjacency = [set() for _ in range(n_tracks)]
    for tracks, values, derivatives in factors:
        tracks = list(tracks)
        values, derivatives = np.asarray(values, float), np.asarray(derivatives, float)
        if len(set(tracks)) != len(tracks) or any(t < 0 or t >= n_tracks for t in tracks):
            raise ValueError('invalid source track support')
        if values.shape != (1 << len(tracks),) or derivatives.shape != (len(values), dimensions):
            raise ValueError('invalid source subset table')
        if values[0] != 0. or np.any(derivatives[0] != 0.) or np.isnan(values).any() or np.isposinf(values).any() or not np.isfinite(derivatives).all():
            raise ValueError('invalid factors')
        checked.append((tracks, values, derivatives))
        for t in tracks:
            adjacency[t].update(set(tracks) - {t})
    remaining, order = set(range(n_tracks)), []
    while remaining:
        t = min(remaining, key=lambda i: (len(adjacency[i] & remaining), i))
        neighbors = adjacency[t] & remaining
        for i in neighbors:
            adjacency[i].update(neighbors - {i})
        order.append(t)
        remaining.remove(t)
    rank = {t: i for i, t in enumerate(order)}
    checked.sort(key=lambda f: (min((rank[t] for t in f[0]), default=n_tracks), len(f[0])))
    future = [0] * (len(checked) + 1)
    for i in range(len(checked) - 1, -1, -1):
        future[i] = future[i + 1] | sum(1 << t for t in checked[i][0])
    full = (1 << n_tracks) - 1
    states = np.arange(full + 1, dtype=np.int64)
    score = np.full(len(states), -np.inf)
    score[0] = 0.
    gradient = np.zeros((len(states), dimensions))
    for stage, (tracks, values, derivatives) in enumerate(checked):
        later = future[stage + 1]
        active = np.flatnonzero(np.isfinite(score))
        new_score, new_gradient = score.copy(), gradient.copy()
        new_score[(states | later) != full] = -np.inf
        for subset in range(1, len(values)):
            if not np.isfinite(values[subset]):
                continue
            mask = sum(1 << t for j, t in enumerate(tracks) if subset & (1 << j))
            previous = active[((active & mask) == 0) & ((active | mask | later) == full)]
            if not len(previous):
                continue
            target = previous | mask
            candidate = score[previous] + values[subset]
            combined = np.logaddexp(new_score[target], candidate)
            weight = np.exp(candidate - combined)
            new_gradient[target] += weight[:, None] * (gradient[previous] + derivatives[subset] - new_gradient[target])
            new_score[target] = combined
        score, gradient = new_score, new_gradient
    return float(score[-1]), gradient[-1]
