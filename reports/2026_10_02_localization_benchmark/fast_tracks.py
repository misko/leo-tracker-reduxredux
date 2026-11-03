"""Vectorized whole-track nuisance fits for localization position searches."""

from __future__ import annotations

import numpy as np

ALIAS_HZ = 1.0 / 4.4e-6
SCALE_HZ = 200.0
CAP_HZ = 2000.0
UNMATCHED_COST = 2 * SCALE_HZ**2 * (np.sqrt(1 + (CAP_HZ / SCALE_HZ) ** 2) - 1)
SATELLITE_COUNT = 64


def _raw_rho(errors):
    scaled = np.asarray(errors, dtype=float) / SCALE_HZ
    return 2 * SCALE_HZ**2 * (np.sqrt(1 + scaled * scaled) - 1)


def _circular(values):
    return (values + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def _stable_argmin_rows(values):
    values = np.asarray(values, dtype=float)
    minimum = np.min(values, axis=1)
    close = np.isclose(values, minimum[:, None], rtol=1e-10, atol=1e-6)
    return np.argmax(close, axis=1).astype(int)


def _line_step(times, values, weights, initial, slope_limit):
    total = float(np.sum(weights))
    if total <= 0:
        return np.asarray(initial, dtype=float)
    mean_time = float(np.sum(weights * times) / total)
    mean_value = float(np.sum(weights * values) / total)
    variance = float(np.sum(weights * (times - mean_time) ** 2))
    slope = float(
        np.clip(
            np.sum(weights * (times - mean_time) * (values - mean_value))
            / max(variance, 1e-20),
            -slope_limit,
            slope_limit,
        )
    )
    return np.array([mean_value - slope * mean_time, slope])


def _padded(blocks):
    block_count = len(blocks)
    visible = np.zeros((block_count, SATELLITE_COUNT), dtype=bool)
    receivers = np.zeros(block_count, dtype=int)
    lengths = np.zeros(block_count, dtype=int)
    residual_parts = []
    time_parts = []
    for index, block in enumerate(blocks):
        block_times = np.asarray(block["times"], dtype=float)
        block_residual = np.asarray(block["residual"], dtype=float)
        block_visible = np.asarray(block["visible"], dtype=bool)
        if block_times.ndim != 1 or not len(block_times):
            raise ValueError("each track block must have nonempty one-dimensional times")
        if block_residual.shape != (len(block_times), SATELLITE_COUNT):
            raise ValueError("each track residual must have shape observations by 64 satellites")
        if block_visible.shape != (SATELLITE_COUNT,):
            raise ValueError("each track visibility vector must have length 64")
        length = len(block_times)
        residual_parts.append(block_residual)
        time_parts.append(block_times)
        visible[index] = block_visible
        receivers[index] = int(block["receiver"])
        lengths[index] = length
    starts = np.r_[0, np.cumsum(lengths[:-1])]
    owners = np.repeat(np.arange(block_count), lengths)
    return {
        "blocks": blocks,
        "residual": (
            np.concatenate(residual_parts)
            if residual_parts
            else np.empty((0, SATELLITE_COUNT), dtype=float)
        ),
        "times": np.concatenate(time_parts) if time_parts else np.empty(0, dtype=float),
        "visible": visible,
        "receivers": receivers,
        "lengths": lengths,
        "starts": starts,
        "owners": owners,
    }


def _independent_arrays(padded):
    residual = padded["residual"]
    lengths = padded["lengths"]
    if not len(lengths):
        return (
            np.empty((0, SATELLITE_COUNT)),
            np.empty((0, SATELLITE_COUNT)),
            np.empty(0, dtype=int),
        )
    starts = padded["starts"]
    owners = padded["owners"]
    locations = np.add.reduceat(residual, starts, axis=0) / lengths[:, None]
    active = np.ones(len(lengths), dtype=bool)
    for _iteration in range(15):
        errors = residual - locations[owners]
        weights = 1.0 / np.sqrt(1 + (errors / SCALE_HZ) ** 2)
        updated = np.add.reduceat(weights * residual, starts, axis=0) / np.maximum(
            np.add.reduceat(weights, starts, axis=0), 1e-20
        )
        change = np.max(np.abs(updated - locations), axis=1)
        locations[active] = updated[active]
        active &= change >= 0.01
        if not np.any(active):
            break
    errors = residual - locations[owners]
    costs = np.add.reduceat(_raw_rho(errors), starts, axis=0) / lengths[:, None]
    costs = np.where(padded["visible"], costs, np.inf)
    selected = _stable_argmin_rows(costs)
    return locations, costs, selected


def fit_track_independent(blocks):
    """Fit one robust offset and one all-64 satellite identity per whole track."""

    padded = _padded(blocks)
    locations, costs, satellites = _independent_arrays(padded)
    selected = []
    for index, block in enumerate(blocks):
        satellite = int(satellites[index])
        start = padded["starts"][index]
        stop = start + padded["lengths"][index]
        cost = float(costs[index, satellite])
        errors = padded["residual"][start:stop, satellite] - locations[index, satellite]
        selected.append(
            {
                **block,
                "satellite": satellite,
                "offset_hz": float(locations[index, satellite]),
                "alias_branch": None,
                "cost": cost,
                "errors": errors,
                "accepted": bool(np.isfinite(cost) and cost < UNMATCHED_COST),
            }
        )
    selected_costs = costs[np.arange(len(blocks)), satellites]
    objective = float(np.mean(np.minimum(selected_costs, UNMATCHED_COST)))
    return objective, selected, {}


def _receiver_line_starts(padded, initial):
    means = (
        np.add.reduceat(padded["residual"], padded["starts"], axis=0)
        / padded["lengths"][:, None]
    )
    folded = _circular(means)[padded["visible"]]
    starts = [np.asarray(initial, dtype=float)]
    if len(folded):
        histogram, edges = np.histogram(
            folded, bins=128, range=(-ALIAS_HZ / 2, ALIAS_HZ / 2)
        )
        for index in np.argsort(-histogram, kind="stable")[:2]:
            starts.append(np.array([(edges[index] + edges[index + 1]) / 2, 0.0]))
    unique = []
    for start in starts:
        if not any(np.linalg.norm(start - previous) < 1e-9 for previous in unique):
            unique.append(start)
    return unique


def _shared_choices(padded, line):
    residual = padded["residual"]
    times = padded["times"]
    lengths = padded["lengths"]
    starts = padded["starts"]
    owners = padded["owners"]
    expected = line[0] + line[1] * times
    difference = residual - expected[:, None]
    branches = np.rint(
        np.add.reduceat(difference, starts, axis=0) / lengths[:, None] / ALIAS_HZ
    )
    errors = difference - branches[owners] * ALIAS_HZ
    costs = np.add.reduceat(_raw_rho(errors), starts, axis=0) / lengths[:, None]
    costs = np.where(padded["visible"], costs, np.inf)
    satellites = _stable_argmin_rows(costs)
    indices = np.arange(len(satellites))
    selected_branches = branches[indices, satellites]
    selected_costs = costs[indices, satellites]
    selected_errors = errors[np.arange(len(errors)), satellites[owners]]
    return satellites, selected_branches, selected_costs, selected_errors


def _fit_receiver_shared(blocks, initial, slope_limit):
    if not blocks:
        return np.asarray(initial, dtype=float), []
    padded = _padded(blocks)
    best = None
    for start in _receiver_line_starts(padded, initial):
        line = start.copy()
        line[1] = np.clip(line[1], -slope_limit, slope_limit)
        for _iteration in range(20):
            satellites, branches, costs, errors = _shared_choices(padded, line)
            accepted = np.isfinite(costs) & (costs < UNMATCHED_COST)
            valid = accepted[padded["owners"]]
            if not np.any(valid):
                break
            values = padded["residual"][
                np.arange(len(padded["residual"])), satellites[padded["owners"]]
            ]
            values -= branches[padded["owners"]] * ALIAS_HZ
            weights = 1.0 / padded["lengths"][padded["owners"]]
            weights = weights / np.sqrt(1 + (errors / SCALE_HZ) ** 2)
            weights *= valid
            updated = _line_step(
                padded["times"][valid],
                values[valid],
                weights[valid],
                line,
                slope_limit,
            )
            change = abs(updated[0] - line[0]) + 150 * abs(updated[1] - line[1])
            line = updated
            if change < 0.05:
                break
        satellites, branches, costs, errors = _shared_choices(padded, line)
        score = float(np.mean(np.minimum(costs, UNMATCHED_COST)))
        if best is None or score < best[0]:
            choices = [
                (
                    int(satellites[index]),
                    float(branches[index]),
                    float(costs[index]),
                    errors[
                        padded["starts"][index] : padded["starts"][index]
                        + padded["lengths"][index]
                    ].copy(),
                )
                for index in range(len(blocks))
            ]
            best = score, line, choices
    return best[1], best[2]


def fit_track_shared(blocks, initial_parameters, slope_limit):
    """Fit receiver-shared constant or slope-bounded line nuisance parameters."""

    initial_parameters = np.asarray(initial_parameters, dtype=float)
    if initial_parameters.shape != (70,):
        raise ValueError("initial_parameters must be a length-70 vector")
    _, independent, _ = fit_track_independent(blocks)
    seeded_parameters = initial_parameters.copy()
    for receiver in (0, 1):
        local = [row for row in independent if row["receiver"] == receiver and row["accepted"]]
        if not local:
            continue
        times = np.asarray([np.mean(row["times"]) for row in local])
        offsets = np.asarray([row["offset_hz"] for row in local])
        initial_line = initial_parameters[2 + 2 * receiver : 4 + 2 * receiver]
        expected = initial_line[0] + initial_line[1] * times
        offsets -= np.rint((offsets - expected) / ALIAS_HZ) * ALIAS_HZ
        seeded_parameters[2 + 2 * receiver : 4 + 2 * receiver] = _line_step(
            times, offsets, np.ones(len(times)), initial_line, slope_limit
        )
    lines = {}
    choice_by_track = {}
    for receiver in (0, 1):
        local = [block for block in blocks if block["receiver"] == receiver]
        initial = seeded_parameters[2 + 2 * receiver : 4 + 2 * receiver]
        line, choices = _fit_receiver_shared(local, initial, slope_limit)
        lines[receiver] = line
        for block, choice in zip(local, choices, strict=True):
            choice_by_track[block["track_index"]] = choice
    selected = []
    for block in blocks:
        satellite, branch, cost, errors = choice_by_track[block["track_index"]]
        selected.append(
            {
                **block,
                "satellite": satellite,
                "offset_hz": float(lines[block["receiver"]][0]),
                "alias_branch": int(branch),
                "cost": cost,
                "errors": errors,
                "accepted": bool(np.isfinite(cost) and cost < UNMATCHED_COST),
            }
        )
    objective = float(np.mean([min(row["cost"], UNMATCHED_COST) for row in selected]))
    return objective, selected, lines


__all__ = ["fit_track_independent", "fit_track_shared"]
