"""Cold robust mixture of orbital and integer-alias predictions for v3 tracks."""

from collections import defaultdict
from itertools import product

import numpy as np
from scipy.special import logsumexp

from leo.analysis.localization_v3.scan import group
from leo.analysis.localization_v3.tracks import active_curvature
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency, prepare_phase_geometry
from leo.analysis.research.retained_track_likelihood import PERIOD


TOP = 8
DF = 4.
ALIAS_NEIGHBORS = np.array([-1, 0, 1])
ARMS = ("c0", "fitted_c")


def profile(raw, tangent, sigma, phase_sigma, *, design=None):
    """Solve Gaussian-prior local offset and bounded tangent phase exactly."""
    n = raw.shape[-1]
    offset_precision = (sigma / 1000.) ** 2
    phase_precision = (sigma / phase_sigma) ** 2
    inv = 1 / (n + offset_precision)
    centers = tangent.sum(axis=-1) * inv
    reduced = tangent - centers[..., None]
    quad = np.sum(reduced * tangent, axis=-1) + phase_precision
    unconstrained = np.sum(reduced * raw, axis=-1) / quad
    phase = np.clip(unconstrained, -15., 15.)
    intercept = (raw - tangent * phase[..., None]).sum(axis=-1) * inv
    residual = raw - tangent * phase[..., None] - intercept[..., None]
    square = (np.sum(residual * residual, axis=-1) + offset_precision * intercept**2
              + phase_precision * phase**2) / sigma**2
    gram = None
    if design is not None:
        # Schur complement of the two local columns. At a phase bound only
        # the offset remains free when the shared receiver model changes.
        projected_cross = reduced @ design
        base = design.T @ design - np.outer(design.sum(axis=0), design.sum(axis=0)) * inv
        open_phase = np.abs(unconstrained) <= 15.
        reduced_rank = np.einsum("...i,...j->...ij", projected_cross, projected_cross)
        gram = base - reduced_rank * (open_phase / quad)[..., None, None]
    return square, phase, intercept, residual, gram


def wrapped(value):
    return (value + PERIOD / 2) % PERIOD - PERIOD / 2


def circular_start(group_count, tracks):
    candidates = [[] for _ in range(group_count)]
    for row in tracks:
        if len(row["labels"]):
            candidates[row["group"]].extend(zip(row["offset"], row["shape"], strict=True))
    result = np.zeros(9)
    for band, raw in enumerate(candidates):
        if not raw:
            continue
        observed, shape = np.asarray(raw).T
        buckets = np.floor((wrapped(observed) / PERIOD + .5) * 48).astype(int) % 48
        mass = np.exp(-.5 * (shape / 450.) ** 2)
        weights = np.bincount(buckets, weights=mass, minlength=48)
        strongest = np.argmax(weights + np.roll(weights, 1) + np.roll(weights, -1))
        distance = (buckets - strongest + 24) % 48 - 24
        near = abs(distance) <= 1
        center = np.angle(np.sum(mass[near] * np.exp(2j * np.pi * observed[near] / PERIOD)))
        result[band] = center / np.pi
    return result


def lane_design(track, times):
    band = group(track)
    design = np.zeros((len(times), 9))
    design[:, band] = PERIOD / 2
    design[:, 4 + band] = (times - 150.) * 5.
    design[:, 8] = (track["rf_hz"] / 1e9 - 11.5) * 200_000.
    return design


def shortlist(tracks, powers, geometry, region, point, sigma):
    latitude, longitude = region.latlon(point)
    frequency, elevation, derivative = phase_linear_frequency(geometry, latitude, (longitude + 180) % 360 - 180)
    result = []
    for track in tracks:
        indices, q = track["indices"], track["q"]
        raw = track["sample"] - q * frequency[:, indices]
        tangent = q * derivative[:, indices]
        centered = raw - raw.mean(axis=-1, keepdims=True)
        change = tangent - tangent.mean(axis=-1, keepdims=True)
        strength = np.sum(change * change, axis=-1) + (sigma / powers) ** 2
        phase = np.clip(np.sum(centered * change, axis=-1) / strength, -15., 15.)
        energy = np.sum((centered - change * phase[:, None]) ** 2, axis=-1)
        shape = np.sqrt((energy + ((sigma / powers) * phase) ** 2) / raw.shape[-1])
        visible = np.all(elevation[:, indices] >= 0., axis=-1)
        order = np.argsort(np.where(visible, shape, np.inf), kind="stable")[:TOP]
        order = order[visible[order]]
        result.append(dict(
            track, labels=order, raw=raw[order], tangent=tangent[order], widths=powers[order],
            offset=(raw.mean(axis=-1) - tangent.mean(axis=-1) * phase)[order], shape=shape[order],
            phase=phase[order],
        ))
    return result


def update(rows, sigma, beta, *, derivatives):
    width = len(beta)
    score = .5 * float(beta @ beta)
    gram, rhs = np.eye(width), -beta.copy()
    records = []
    for row in rows:
        design = row["design"][:, :width]
        n = len(design)
        raw = row["raw"] - design @ beta
        center = raw.mean(axis=-1) - row["tangent"].mean(axis=-1) * row["phase"]
        alias = np.rint(-center / PERIOD).astype(int)[:, None] + ALIAS_NEIGHBORS
        square, phase, offset, residual, local_gram = profile(
            raw[:, None, :] + PERIOD * alias[..., None], row["tangent"][:, None, :],
            sigma, row["widths"][:, None], design=design if derivatives else None,
        )
        z = row["sample"] - row["sample"].mean()
        null = np.log(.1) + n * np.log(sigma / 450.) - .5 * (DF + n) * np.log1p((z @ z) / (DF * 450.**2))
        prior = np.log(.9 / max(1, alias.size))
        log_terms = prior - .5 * (DF + n) * np.log1p(square / DF)
        total = logsumexp(np.append(log_terms.ravel(), null))
        probability = np.exp(log_terms - total)
        score -= total
        if derivatives:
            weight = probability * ((DF + n) / (DF + square)) / sigma**2
            gram += np.sum(weight[..., None, None] * local_gram, axis=(0, 1))
            rhs += np.sum(weight[..., None] * (residual @ design), axis=(0, 1))
        if not probability.size:
            records.append(None)
            continue
        sat, cycle = np.unravel_index(np.argmax(probability), probability.shape)
        records.append(dict(index=int(row["labels"][sat]), alias=int(alias[sat, cycle]),
                            phase_s=float(phase[sat, cycle]), bias_hz=float(offset[sat, cycle]),
                            rms_hz=float(np.sqrt(np.mean(residual[sat, cycle] ** 2))),
                            weight=float(probability[sat, cycle]), null=float(np.exp(null - total))))
    return score, records, gram, rhs


def fit_node(rows, sigma, *, arms=ARMS):
    estimates = {}
    starts = (np.zeros(9), circular_start(4, rows))
    for arm in arms:
        width = 8 + int(arm == "fitted_c")
        fits = []
        for start in starts:
            beta = start[:width].copy()
            for _ in range(3):
                _, _, gram, rhs = update(rows, sigma, beta, derivatives=True)
                beta = np.clip(beta + np.linalg.solve(gram, rhs), -1., 1.)
            score, nominations, _, _ = update(rows, sigma, beta, derivatives=False)
            fits.append(dict(score=score, nominations=nominations, receiver_prior_units=beta.tolist()))
        estimates[arm] = min(fits, key=lambda fit: fit["score"])
    return estimates


def qualified(record):
    return record is not None and record["weight"] > record["null"] and record["rms_hz"] <= 450.


def propose(prepared, region, *, arms=ARMS):
    if arms not in (ARMS, ("c0",)):
        raise ValueError("Expected paired calibration or the fixed-zero cold proposal")
    if prepared["status"] != "inputs_prepared":
        return dict(status=prepared["status"], arms={})
    bank = prepared["sky"]["bank"]
    catalogue = bank["norad"]
    sigma = float(prepared["noise"]["constant_radio_sigma_hz"])
    tracks = []
    for track in prepared["tracks"]["tracks"]:
        times, values = np.asarray(track["times"]), np.asarray(track["values"])
        if not active_curvature(dict(track, times=times, values=values)):
            continue
        choose = np.linspace(0, len(times) - 1, min(9, len(times)), dtype=int)
        sample = times[choose]
        tracks.append(dict(key=track["key"], times=sample, sample=values[choose], design=lane_design(track, sample),
                           group=group(track), q=track["rf_hz"] / 11.5e9, receiver=track["receiver"],
                           observations=list(track["observation_ids"])))
    if not tracks or not len(catalogue):
        return dict(status="no_curved_causal_support", arms={})
    times = np.unique(np.concatenate([track["times"] for track in tracks]))
    for track in tracks:
        track["indices"] = np.searchsorted(times, track["times"])
    geometry = prepare_phase_geometry(bank, times)
    powers = np.maximum(1., bank["phase_sigma_s"])
    cache = {}
    union = defaultdict(set)

    def at(point):
        point = tuple(point)
        if point not in cache:
            hypotheses = shortlist(tracks, powers, geometry, region, point, sigma)
            indices = [row["labels"] for row in hypotheses]
            for track, labels in zip(tracks, indices, strict=True):
                union[track["key"]].update(int(catalogue[j]) for j in labels)
            cache[point] = fit_node(hypotheses, sigma, arms=arms), indices
        return cache[point]

    radius = region.half_width_km
    mesh = list(product(np.linspace(-radius, radius, 5), repeat=2))
    for point in mesh:
        at(point)
    starts = [min(mesh, key=lambda point: at(point)[0][arm]["score"]) for arm in arms]
    for start in starts:
        for delta in product((-radius / 8, 0., radius / 8), repeat=2):
            at(np.clip(np.array(start) + delta, -radius, radius))
    solutions = {}
    for arm in arms:
        point = min(cache, key=lambda point: at(point)[0][arm]["score"])
        fits, labels = at(point)
        selected = []
        for track, indices, record in zip(tracks, labels, fits[arm]["nominations"], strict=True):
            row = {k: track[k] for k in ("key", "observations", "receiver")}
            row["shortlist"] = [int(catalogue[j]) for j in indices]
            row["region_union"] = sorted(union[track["key"]])
            if record is not None:
                row.update(record, norad=int(catalogue[record["index"]]), retained=qualified(record))
            else:
                row["retained"] = False
            selected.append(row)
        support = [row for row in selected if row["retained"]]
        points = np.array([len(row["observations"]) for row in support])
        solutions[arm] = dict(
            east_north_km=list(point), latlon=list(region.latlon(point)), score=fits[arm]["score"],
            rf_rms_hz=None if not support else float(np.sqrt(np.average(
                [row["rms_hz"] ** 2 for row in support], weights=points))),
            sampled_owner_points=int(points.sum()), families=len({row["norad"] for row in support}),
            receivers=len({row["receiver"] for row in support}), tracks=selected,
            receiver_prior_units=fits[arm]["receiver_prior_units"],
        )
    common = solutions["c0"]["tracks"]
    for solution in solutions.values():
        latitude, longitude = solution["latlon"]
        frequency, _, derivative = phase_linear_frequency(geometry, latitude, (longitude + 180) % 360 - 180)
        beta = np.asarray(solution["receiver_prior_units"])
        squared, count = 0., 0
        for track, label in zip(tracks, common, strict=True):
            if not label["retained"]:
                continue
            j, indices, q = label["index"], track["indices"], track["q"]
            raw = (track["sample"] - q * frequency[j, indices] + PERIOD * label["alias"]
                   - track["design"][:, :len(beta)] @ beta)
            _, _, _, residual, _ = profile(raw, q * derivative[j, indices], sigma, powers[j])
            squared += residual @ residual
            count += len(residual)
        solution["matched_sample_rms_hz"] = None if not count else float(np.sqrt(squared / count))
        solution["matched_sample_points"] = count
    return dict(status="complete", catalogue=[int(j) for j in catalogue], node_count=len(cache),
                curved_points=sum(len(t["observations"]) for t in tracks), track_count=len(tracks),
                full_catalogue_cells=len(catalogue) * len(cache) * len(tracks), arms=solutions)
