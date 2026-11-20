"""Sparse second-order path packing for the bounded native GLRT replay."""

import numpy as np
from numpy.polynomial import polynomial as poly

METHOD = "native_simple_tracks"
CONTROL = "native_simple_tracks_graph"
CURVATURE_LIMIT = 600.0
CURVATURE_SCALE = 20.0
MAX_PREDECESSORS = 48


def wrap(value, period):
    return (value + period / 2) % period - period / 2


def edges(t, y, gap, slope, period):
    if gap * slope >= period / 2:
        raise ValueError("slope and gap permit multiple alias branches")
    # Keep at most 48 evenly distributed chronological predecessors per node.
    first = np.searchsorted(t, t - gap)
    stop = np.searchsorted(t, t - 0.15, side="right")
    counts = np.minimum(stop - first, MAX_PREDECESSORS)
    target = np.repeat(np.arange(len(t)), counts)
    repeated = np.repeat(counts, counts)
    offset = np.arange(len(target)) - np.repeat(np.cumsum(counts) - counts, counts)
    distance = np.maximum(0, stop - first - 1)
    source = first[target] + offset * distance[target] // np.maximum(1, repeated - 1)
    dt = t[target] - t[source]
    v = wrap(y[target] - y[source], period) / dt
    good = np.abs(v) <= slope
    source, target, dt, v = (a[good] for a in (source, target, dt, v))
    by_source = np.argsort(source, kind="stable")
    keys = np.arange(len(t) + 1)
    incoming = np.searchsorted(target, keys)
    outgoing = np.searchsorted(source, keys, sorter=by_source)
    return source, target, dt, v, incoming, outgoing, by_source


def path(t, y, graph, allowed, cfg):
    source, target, dt, velocity, incoming, outgoing, by_source = graph
    score = np.full(len(source), -np.inf)
    head, parent, count = (np.full(len(score), -1, dtype=int) for _ in range(3))
    reward = cfg["association_sigma"] ** 2
    noise2 = 2 * cfg["noise_sigma_hz"] ** 2
    for node in range(len(t)):
        after = by_source[outgoing[node] : outgoing[node + 1]]
        after = after[allowed[after]]
        if not len(after):
            continue
        gap = 0.05 * dt[after]
        score[after] = 2 * reward - cfg["track_penalty"] - gap
        count[after], head[after] = 2, node
        before = np.arange(incoming[node], incoming[node + 1])
        before = before[allowed[before]]
        if not len(before):
            continue
        a, b = dt[before, None], dt[None, after]
        variance = noise2 * (1 / a**2 + 1 / b**2 + 1 / (a * b))
        variance += (CURVATURE_SCALE * (a + b) / 2) ** 2
        turn = velocity[before, None] - velocity[None, after]
        candidates = score[before, None] + reward - gap - 2 * turn**2 / variance
        winner = candidates.argmax(axis=0)
        value = candidates[winner, np.arange(len(after))]
        take = value > score[after]
        choose, prior = after[take], before[winner[take]]
        score[choose], head[choose], count[choose] = value[take], head[prior], count[prior] + 1
        parent[choose] = prior
    admissible = np.flatnonzero(
        (count >= cfg["min_points"]) & (t[target] - t[head] >= cfg["min_span_s"]) & (score > 0)
    )
    if not len(admissible):
        return None
    last = admissible[score[admissible].argmax()]
    chain = []
    while last >= 0:
        chain.append(last)
        last = parent[last]
    chain = np.array(chain[::-1])
    ids = np.r_[source[chain[0]], target[chain]]
    return ids, y[ids[0]] + np.r_[0, np.cumsum(velocity[chain] * dt[chain])], chain


def measure_bound(coeff, low, high, order):
    value = poly.polyder(coeff, m=order)
    roots = poly.polyroots(poly.polyder(value))
    interior = roots.real[(np.abs(roots.imag) < 1e-10) & (roots.real > low) & (roots.real < high)]
    return np.max(np.abs(poly.polyval(np.r_[low, high, interior], value)))


def model(t, ids, values, cfg):
    if len(ids) < cfg["min_points"] or t[ids[-1]] - t[ids[0]] < cfg["min_span_s"]:
        return None
    center = (t[ids[0]] + t[ids[-1]]) / 2
    scale = max(t[ids[-1]] - center, 1)
    x = (t[ids] - center) / scale
    degree = min(cfg["max_degree"], len(ids) // cfg["points_per_coefficient"] - 1)
    design = poly.polyvander(x, degree)
    best, score = None, np.inf
    for d in range(degree + 1):
        basis = design[:, : d + 1]
        coeff = np.linalg.lstsq(basis, values, rcond=None)[0]
        residual = values - basis @ coeff
        cost = residual @ residual / cfg["noise_sigma_hz"] ** 2 + (d + 1) * np.log(len(ids))
        if (
            cost < score
            and measure_bound(coeff, x[0], x[-1], 1) <= cfg["max_slope_hz_s"] * scale
            and measure_bound(coeff, x[0], x[-1], 2) <= CURVATURE_LIMIT * scale**2
        ):
            best, score = (center, scale, coeff), cost
    return best


def predict(fit, times):
    center, scale, coeff = fit
    return poly.polyval((times - center) / scale, coeff)


def support(t, y, available, ids, seed, cfg):
    gap, period = cfg["max_gap_s"], cfg["alias_spacing_hz"]
    gate = cfg["association_sigma"] * cfg["noise_sigma_hz"]
    candidates = np.flatnonzero(available & (t >= t[ids[0]] - gap) & (t <= t[ids[-1]] + gap))
    fit = model(t, ids, seed, cfg)
    for _ in range(3):
        if fit is None:
            return None
        pred = predict(fit, t[candidates])
        eligible = candidates[np.abs(wrap(y[candidates] - pred, period)) < gate]
        chunks = np.split(eligible, np.flatnonzero(np.diff(t[eligible]) > gap) + 1)
        selected = max(chunks, key=lambda c: (np.count_nonzero(np.isin(c, ids)), len(c)))
        if np.array_equal(selected, ids):
            return ids, fit
        ids = selected
        pred = predict(fit, t[ids])
        fit = model(t, ids, pred + wrap(y[ids] - pred, period), cfg)
    if fit is not None and np.max(np.abs(wrap(y[ids] - predict(fit, t[ids]), period))) < gate:
        return ids, fit
    return None


def fit_lane(t, y, cfg):
    if len(t) < cfg["min_points"] or t[-1] - t[0] < cfg["min_span_s"]:
        return []
    period = cfg["alias_spacing_hz"]
    graph = edges(t, y, cfg["max_gap_s"], cfg["max_slope_hz_s"], period)
    source, target = graph[:2]
    enabled = np.ones(len(source), bool)
    available = np.ones(len(t), bool)
    models = []
    for _ in range(2 * cfg["max_tracks"]):
        choice = path(t, y, graph, enabled & available[source] & available[target], cfg)
        if choice is None or len(models) == cfg["max_tracks"]:
            break
        ids, seed, chain = choice
        enabled[chain] = False
        candidate = support(t, y, available, ids, seed, cfg)
        if candidate is not None:
            members, fit = candidate
            available[members] = False
            models.append((members, fit))
    # Close competing curves cannot both explain a crossing sample. Keep
    # the velocity-continuous owner if its residual beats the other by a sigma.
    tracks = []
    for k, (ids, fit) in enumerate(models):
        pred = predict(fit, t[ids])
        own = np.abs(wrap(y[ids] - pred, period))
        clear = np.ones(len(ids), bool)
        for j, (other, curve) in enumerate(models):
            if k == j or t[other[-1]] < t[ids[0]] or t[other[0]] > t[ids[-1]]:
                continue
            active = (t[ids] >= t[other[0]]) & (t[ids] <= t[other[-1]])
            rival = np.abs(wrap(y[ids[active]] - predict(curve, t[ids[active]]), period))
            clear[active] &= rival - own[active] >= cfg["noise_sigma_hz"]
        selected = ids[clear]
        for chunk in np.split(
            selected, np.flatnonzero(np.diff(t[selected]) > cfg["max_gap_s"]) + 1
        ):
            if len(chunk) >= cfg["min_points"] and t[chunk[-1]] - t[chunk[0]] >= cfg["min_span_s"]:
                predicted = predict(fit, t[chunk])
                gauge = np.floor((predicted[0] + period / 2) / period)
                lifted = y[chunk] + (np.rint((predicted - y[chunk]) / period) - gauge) * period
                tracks.append((chunk, lifted))
    return tracks


def projection(lanes, configuration):
    tracks = []
    for (rf, receiver, channel), points in sorted(lanes.items()):
        t, y = np.asarray(points, dtype=np.float64).T
        for ids, values in fit_lane(t, y, configuration):
            tracks.append(
                dict(
                    times=t[ids].tolist(),
                    values=values.tolist(),
                    receiver=receiver,
                    channel=channel,
                    rf_hz=rf,
                )
            )
    return tracks
