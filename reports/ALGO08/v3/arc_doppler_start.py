"""Use six observations per arc to propose one full-objective cold start."""

import numpy as np


NODES = 6
MAX_LOSS = 9.
MIN_CURVATURE = .05
PROBES = np.array(((0., 0.), (-1., 0.), (1., 0.), (0., -1.), (0., 1.)))


def arcs(tracks, curved):
    """Take the longest arc per receiver, RF bank, and third of the time span."""
    if not curved:
        return []
    first = min(float(tracks[i]["times"][0]) for i in curved)
    last = max(float(tracks[i]["times"][-1]) for i in curved)
    chosen = {}
    for i in curved:
        track = tracks[i]
        times = np.asarray(track["times"])
        if len(times) < NODES or not last > first:
            continue
        third = min(2, int(3 * ((times[0] + times[-1]) / 2 - first) / (last - first)))
        key = track["receiver"], int(track["channel"] >= 5), third
        rank = float(times[-1] - times[0]), len(times)
        if key not in chosen or rank > chosen[key][0]:
            chosen[key] = rank, i
    return [(key, chosen[key][1]) for key in sorted(chosen)]


def contrast(values, predicted, tangent, elevation, sigma):
    """Profile a causal phase tangent from three disjoint centred differences."""
    noise = 150. * np.sqrt(2.)
    residual = (values - predicted) / noise
    diff = residual[:, :3] - residual[:, 3:][:, ::-1]
    h = (tangent[:, :3] - tangent[:, 3:][:, ::-1]) / noise
    prior = 1 / sigma**2
    phase = np.clip(np.sum(diff * h, axis=1) / (np.sum(h*h, axis=1) + prior), -15., 15.)
    error = diff - phase[:, None] * h
    cost = (np.sum(error*error, axis=1) + prior*phase**2) / 3
    return np.where(np.all(elevation >= 0, axis=1), cost, np.inf), phase


def select(stencil, radius):
    """Find an interior stationary point of the symmetric axis stencil."""
    center, west, east, south, north = stencil
    curved = np.array([west + east, south + north]) - 2*center
    if not np.isfinite(stencil).all() or np.any(curved < MIN_CURVATURE):
        return None, "flat_or_indefinite"
    target = .5 * radius * np.array([west-east, south-north]) / curved
    if np.any(np.abs(target) > .8 * radius):
        return None, "edge_or_outside"
    return target, None


def propose(scan):
    from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
    from leo.analysis.research.retained_track_likelihood import PERIOD

    picked = arcs(scan.tracks, scan.curved)
    evidence = dict(catalogue=len(scan.norads), active_arcs=len(scan.curved), used_arcs=len(picked),
                    keys=[scan.tracks[i]["key"] for _, i in picked], point=None)
    if len(picked) < 3 or any(len({key[k] for key, _ in picked}) < 2 for k in (0, 2)):
        return dict(evidence, abstain="insufficient_receiver_or_time_support")

    sampled = []
    for key, i in picked:
        track = scan.tracks[i]
        ix = np.rint(np.linspace(0, len(track["times"]) - 1, NODES)).astype(int)
        sampled.append((key, track["times"][ix], track["values"][ix], track["rf_hz"] / 11.5e9))
    times = np.unique(np.concatenate([t for _, t, _, _ in sampled]))
    geometry = prepare_phase_geometry(scan.sky, times)
    indexed = [(key, np.searchsorted(times, t), y, q) for key, t, y, q in sampled]

    def score(xy):
        f, e, derivative = phase_linear_frequency(geometry, *scan.search_region.latlon(xy))
        minima, shortlists, phase, intercept = [], [], [], []
        for _, indices, y, q in indexed:
            predicted, tangent = q*f[:, indices], q*derivative[:, indices]
            cost, offset = contrast(y, predicted, tangent, e[:, indices], scan.sigma)
            top = np.argsort(cost, kind="stable")[:4]
            usable = top[np.isfinite(cost[top])]
            shortlists.append(usable.tolist())
            winner = int(top[0])
            minima.append(float(min(cost[winner], MAX_LOSS)))
            phase.append(float(offset[winner]))
            intercept.append(float(np.mean(y-predicted[winner]-offset[winner]*tangent[winner])))
        return np.array(minima), shortlists, phase, np.array(intercept)

    radius = scan.search_region.half_width_km
    measures = [score(point) for point in PROBES*radius]
    stencil = np.array([part[0].mean() for part in measures])
    point, abstain = select(stencil, radius)
    if point is not None:
        objective, shortlist, phases, intercept = score(point)
        measures.append((objective, shortlist, phases, intercept))
        for receiver in (1, 2):
            mask = [key[0] == receiver for key, _, _, _ in indexed]
            if objective[mask].mean() > measures[0][0][mask].mean() + .25:
                abstain = "receiver_disagreement"
        if objective.mean() > stencil[0] or stencil[1:].min() - objective.mean() < MIN_CURVATURE:
            abstain = "no_clear_interior_gain"
    best = int(stencil.argmin())
    _, slate, _, offsets = measures[-1] if abstain is None else measures[best]
    beta = np.zeros(8)
    for receiver, bank in {(key[0], key[1]) for key, _, _, _ in indexed}:
        mask = [bool(support) and key[:2] == (receiver, bank)
                for (key, _, _, _), support in zip(indexed, slate, strict=True)]
        if sum(mask) >= 2:
            mean = np.mean(np.exp(2j*np.pi*offsets[mask]/PERIOD))
            if abs(mean) >= .55:
                beta[2*(receiver-1)+bank] = PERIOD*np.angle(mean)/(2*np.pi)
    shortlist = {track: sorted(set().union(*(m[1][k] for m in measures)))
                 for k, track in enumerate(evidence["keys"])}
    return dict(evidence, abstain=abstain, slope_scores=stencil, compact_times=len(times),
                tested_locations=len(measures), point=point if abstain is None else None,
                diagnostic_point=point if abstain is None else PROBES[best]*radius,
                shortlisted_labels=shortlist, beta=beta)
