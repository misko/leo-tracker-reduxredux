import numpy as np

ALIAS_HZ = 1 / 4.4e-6
SCALE_HZ = 200.0
UNMATCHED_COST = 2 * SCALE_HZ**2 * (np.sqrt(1 + (2000 / SCALE_HZ) ** 2) - 1)


def loss(residual):
    return 2 * SCALE_HZ**2 * (np.sqrt(1 + (residual / SCALE_HZ) ** 2) - 1)


def bounded_line(times, values, weights, limit):
    total = weights.sum()
    if total <= 0:
        return 0.0, 0.0
    mean_time = np.sum(weights * times) / total
    mean_value = np.sum(weights * values) / total
    variance = np.sum(weights * (times - mean_time) ** 2)
    slope = np.sum(weights * (times - mean_time) * (values - mean_value)) / max(variance, 1e-20)
    slope = float(np.clip(slope, -limit, limit))
    return float(mean_value - slope * mean_time), slope


def choose(residual, mask, times, intercept, slope, visible):
    count = np.maximum(mask.sum(axis=1), 1)
    difference = residual - (intercept + slope * times)[:, None, :]
    branches = np.rint(np.sum(difference * mask[:, None, :], axis=2) / count[:, None] / ALIAS_HZ)
    errors = difference - branches[:, :, None] * ALIAS_HZ
    costs = np.sum(loss(errors) * mask[:, None, :], axis=2) / count[:, None]
    costs = np.where(visible, costs, np.inf)
    selected = np.argmin(costs, axis=1)
    row = np.arange(len(selected))
    return selected, branches[row, selected], costs[row, selected]


def fit_shared(residual, times, mask, visible, limit):
    counts = np.maximum(mask.sum(axis=1), 1)
    means = np.sum(residual * mask[:, None, :], axis=2) / counts[:, None]
    folded = (means + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2
    seeds = folded[visible]
    if not len(seeds):
        return dict(
            intercept=0.0,
            slope=0.0,
            selected=np.zeros(len(times), dtype=int),
            branches=np.zeros(len(times)),
            costs=np.full(len(times), np.inf),
        )
    distances = (folded[None, :, :] - seeds[:, None, None] + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2
    consensus = np.sum(np.any((np.abs(distances) < 3000) & visible[None, :, :], axis=2), axis=1)
    starts = []
    for index in np.argsort(-consensus, kind="stable"):
        if all(
            abs((seeds[index] - old + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2) > 1000
            for old in starts
        ):
            starts.append(float(seeds[index]))
        if len(starts) == 3:
            break
    best = None
    for intercept in starts:
        slope = 0.0
        for _iteration in range(20):
            selected, branches, costs = choose(residual, mask, times, intercept, slope, visible)
            values = residual[np.arange(len(times)), selected] - branches[:, None] * ALIAS_HZ
            errors = values - intercept - slope * times
            weights = mask / counts[:, None] / np.sqrt(1 + (errors / SCALE_HZ) ** 2)
            weights *= (costs < UNMATCHED_COST)[:, None]
            if not np.any(weights):
                break
            updated_intercept, updated_slope = bounded_line(times, values, weights, limit)
            change = abs(updated_intercept - intercept) + 150 * abs(updated_slope - slope)
            intercept, slope = updated_intercept, updated_slope
            if change < 0.01:
                break
        selected, branches, costs = choose(residual, mask, times, intercept, slope, visible)
        score = float(np.mean(np.minimum(costs, UNMATCHED_COST)))
        if best is None or score < best[0]:
            best = (
                score,
                dict(
                    intercept=intercept,
                    slope=slope,
                    selected=selected,
                    branches=branches,
                    costs=costs,
                ),
            )
    return best[1]


def fit_independent(residual, mask, visible):
    count = np.maximum(mask.sum(axis=1), 1)
    offsets = np.sum(residual * mask[:, None, :], axis=2) / count[:, None]
    for _iteration in range(20):
        errors = residual - offsets[:, :, None]
        weights = mask[:, None, :] / np.sqrt(1 + (errors / SCALE_HZ) ** 2)
        updated = np.sum(weights * residual, axis=2) / np.maximum(weights.sum(axis=2), 1e-20)
        change = np.max(np.abs(updated - offsets))
        offsets = updated
        if change < 0.01:
            break
    costs = np.sum(loss(residual - offsets[:, :, None]) * mask[:, None, :], axis=2) / count[:, None]
    costs = np.where(visible, costs, np.inf)
    selected = np.argmin(costs, axis=1)
    row = np.arange(len(selected))
    return dict(offsets=offsets[row, selected], selected=selected, costs=costs[row, selected])
