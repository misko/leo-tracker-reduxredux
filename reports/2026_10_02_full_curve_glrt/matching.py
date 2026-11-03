import numpy as np

ALIAS_HZ = 1 / 4.4e-6


def circular_residual(measured, prediction):
    return (measured - prediction + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def assign_groups(residual, groups, gate_hz=1000, separation_hz=250):
    unique, inverse = np.unique(groups, return_inverse=True)
    scores = np.full((len(unique), residual.shape[0]), np.inf)
    for satellite in range(residual.shape[0]):
        np.minimum.at(scores[:, satellite], inverse, np.abs(residual[satellite]))
    ranking = np.argsort(scores, axis=1, kind="stable")
    chosen = ranking[:, 0]
    cost = scores[np.arange(len(unique)), chosen]
    runner = (
        scores[np.arange(len(unique)), ranking[:, 1]]
        if residual.shape[0] > 1
        else np.full(len(unique), np.inf)
    )
    point_cost = np.abs(residual[chosen[inverse], np.arange(len(groups))])
    order = np.lexsort((np.arange(len(groups)), point_cost, inverse))
    first = np.r_[True, np.diff(inverse[order]) != 0]
    rows = order[first]
    assert np.array_equal(inverse[rows], np.arange(len(unique)))
    gap = np.zeros(len(unique))
    finite = np.isfinite(cost)
    gap[finite] = runner[finite] - cost[finite]
    accepted = finite & (cost <= gate_hz) & (gap >= separation_hz)
    return {
        "rows": rows,
        "satellites": chosen,
        "error_hz": residual[chosen, rows],
        "gap_hz": gap,
        "accepted": accepted,
    }


def connected_support(assignment, times, channels, receivers, max_gap=4, min_points=8, min_span=10):
    coherent = np.zeros(len(assignment["rows"]), dtype=bool)
    segments = []
    rows = assignment["rows"]
    keys = np.column_stack([assignment["satellites"], channels[rows], receivers[rows]])
    for key in np.unique(keys[assignment["accepted"]], axis=0):
        indices = np.flatnonzero(assignment["accepted"] & np.all(keys == key, axis=1))
        indices = indices[np.argsort(times[rows[indices]])]
        splits = np.flatnonzero(np.diff(times[rows[indices]]) > max_gap) + 1
        for section in np.split(indices, splits):
            start, end = times[rows[section[[0, -1]]]]
            if len(section) < min_points or end - start < min_span:
                continue
            coherent[section] = True
            segments.append(
                {
                    "satellite_index": int(key[0]),
                    "channel": int(key[1]),
                    "receiver": int(key[2]),
                    "start_s": float(start),
                    "end_s": float(end),
                    "points": len(section),
                    "max_gap_s": float(np.max(np.diff(times[rows[section]]))),
                    "indices": section.tolist(),
                }
            )
    return coherent, segments


def robust_line(times, values, weights, initial, limit=10):
    intercept, slope = initial
    for _iteration in range(50):
        residual = values - intercept - slope * times
        effective = weights / np.sqrt(1 + (residual / 200) ** 2)
        mean_time = np.average(times, weights=effective)
        mean_value = np.average(values, weights=effective)
        variance = np.sum(effective * (times - mean_time) ** 2)
        updated_slope = np.clip(
            np.sum(effective * (times - mean_time) * (values - mean_value)) / max(variance, 1e-20),
            -limit,
            limit,
        )
        updated_intercept = mean_value - updated_slope * mean_time
        change = abs(updated_intercept - intercept) + 150 * abs(updated_slope - slope)
        intercept, slope = updated_intercept, updated_slope
        if change < 0.01:
            break
    return float(intercept), float(slope)
