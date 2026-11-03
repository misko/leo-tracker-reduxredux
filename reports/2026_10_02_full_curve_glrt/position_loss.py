import numpy as np
from matching import ALIAS_HZ, circular_residual

SCALE_HZ = 200.0
CAP_HZ = 2000.0


def training_mask(group_times, all_training=False):
    if all_training:
        return np.ones(len(group_times), dtype=bool)
    return (np.floor(np.asarray(group_times) / 10).astype(int) % 3) != 2


def rho(errors):
    return 2 * SCALE_HZ**2 * (np.sqrt(1 + (np.minimum(np.abs(errors), CAP_HZ) / SCALE_HZ) ** 2) - 1)


def best_group_rows(residual, groups):
    satellites = np.argmin(np.abs(residual), axis=1)
    errors = residual[np.arange(len(groups)), satellites]
    ordering = np.lexsort((np.arange(len(groups)), np.abs(errors), groups))
    first = np.r_[True, np.diff(groups[ordering]) != 0]
    rows = ordering[first]
    return rows, satellites[rows], errors[rows]


def line_step(times, values, weights, initial, limit=10):
    if weights.sum() == 0:
        return initial
    mean_time = np.average(times, weights=weights)
    mean_value = np.average(values, weights=weights)
    variance = np.sum(weights * (times - mean_time) ** 2)
    slope = np.clip(
        np.sum(weights * (times - mean_time) * (values - mean_value)) / max(variance, 1e-20),
        -limit,
        limit,
    )
    return np.array([mean_value - slope * mean_time, slope])


def profile_receiver(base_residual, groups, times, training, initial):
    means = circular_residual(base_residual[training] - initial[1] * times[training, None], 0)
    finite = means[np.isfinite(means)]
    starts = [np.array(initial, dtype=float)]
    if len(finite):
        histogram, edges = np.histogram(finite, bins=128, range=(-ALIAS_HZ / 2, ALIAS_HZ / 2))
        for index in np.argsort(-histogram)[:2]:
            starts.append(np.array([(edges[index] + edges[index + 1]) / 2, 0.0]))
    best = None
    for parameters in starts:
        for _iteration in range(15):
            residual = circular_residual(
                base_residual, (parameters[0] + parameters[1] * times)[:, None]
            )
            residual[~np.isfinite(base_residual)] = np.inf
            rows, satellites, errors = best_group_rows(residual, groups)
            use = training[rows] & np.isfinite(errors) & (np.abs(errors) < CAP_HZ)
            selected = rows[use]
            finite_errors = errors[use]
            values = finite_errors + parameters[0] + parameters[1] * times[selected]
            weights = 1 / np.sqrt(1 + (finite_errors / SCALE_HZ) ** 2)
            updated = line_step(times[selected], values, weights, parameters)
            change = abs(updated[0] - parameters[0]) + 150 * abs(updated[1] - parameters[1])
            parameters = updated
            if change < 0.05:
                break
        residual = circular_residual(
            base_residual, (parameters[0] + parameters[1] * times)[:, None]
        )
        residual[~np.isfinite(base_residual)] = np.inf
        rows, _, errors = best_group_rows(residual, groups)
        cost = float(np.mean(rho(errors[training[rows]])))
        if best is None or cost < best[0]:
            best = (cost, parameters)
    return best[1]
