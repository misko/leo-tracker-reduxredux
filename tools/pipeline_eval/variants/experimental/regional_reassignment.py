"""A matched, all-track orbit-mixture score on both sides of an offered square."""

import numpy as np

from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import NOISE, PERIOD
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from leo.sky.propagation import ElementSetCatalogue


RADII = dict(inside=(1 / 8, 1 / 4, 3 / 8, 1 / 2 - 1 / 256),
             exterior=(1 / 2 + 1 / 256, 5 / 8, 3 / 2, 5 / 2))
NORMALS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def probes(region):
    """Equal-sized sets with the same face normals and tangential offsets."""
    for side, radii in RADII.items():
        for radius in radii:
            for normal in map(np.asarray, NORMALS):
                lateral = np.array((-normal[1], normal[0]))
                for offset in (-1 / 5, 0, 1 / 5):
                    point = (radius * normal + offset * lateral) * region.width_km
                    latlon = tuple(map(float, region.latlon(point)))
                    if not (-90 < latlon[0] < 90 and -180 <= latlon[1] <= 180):
                        raise ValueError("Regional probes exceed the local geographic domain")
                    yield dict(side=side, xy_km=point.tolist(), latlon=latlon)


def possible_horizon(position, center, locations):
    """Bound all probe elevations using one observer and the largest normal displacement."""
    origin = geodetic_to_ecef_km(*center, 0)
    up = ecef_to_enu_matrix(*center)[2]
    observing = np.asarray([geodetic_to_ecef_km(*loc, 0) for loc in locations])
    normals = np.asarray([ecef_to_enu_matrix(*loc)[2] for loc in locations])
    delta = np.linalg.norm(normals - up, axis=1).max()
    height = np.max(np.abs(np.einsum("ij,ij->i", observing, normals) - origin @ up))
    rough = position @ up - origin @ up + np.linalg.norm(position, axis=-1) * delta + height
    return rough >= -1e-8


def select(catalogue, mask):
    indices = np.flatnonzero(mask)
    return ElementSetCatalogue(tuple(catalogue.names[i] for i in indices),
                               tuple(catalogue.satellite_numbers[i] for i in indices),
                               tuple(catalogue.satellites[i] for i in indices))


def orbit_geometry(catalogue, origin, times, starts, center, locations):
    # Visibility at the first observation is necessary for an entire track.
    # Include the exact surrounding integer knots used by the full score.
    left = np.floor(starts)
    knots = np.unique(np.r_[left[0] - 1, left, left + 1])
    p, v, good = ecef_states(catalogue, origin, knots)
    first, _ = phase_shifted_states(dict(time_s=knots, position_km=p[good], velocity_km_s=v[good]),
                                    starts, 0.0)
    common = possible_horizon(first, center, locations).any(axis=1)
    candidates = select(select(catalogue, good), common)
    if not len(candidates):
        return None, np.empty(0, dtype=int)
    knots = np.arange(np.floor(times[0] - .05), np.ceil(times[-1] + .05) + 1)
    p, v, usable = ecef_states(candidates, origin, knots)
    full = dict(time_s=knots, position_km=p[usable], velocity_km_s=v[usable])
    geometry = prepare_phase_geometry(full, times) if np.any(usable) else None
    return geometry, np.asarray(candidates.satellite_numbers)[usable]


def contrast_log_ratio(observed, predicted, phase_derivative):
    """Marginal Gaussian track contrasts against uniform native-period contrasts."""
    count = len(observed)
    raw = (observed - predicted) / NOISE
    raw -= raw.mean(axis=1, keepdims=True)
    phase = (phase_derivative - phase_derivative.mean(axis=1, keepdims=True)) / NOISE
    # The nominal causal-phase prior has 1 s standard deviation.
    variance = 1 + np.sum(phase * phase, axis=1)
    rhs = np.sum(raw * phase, axis=1)
    innovation = raw - phase * (rhs / variance)[:, None]
    quadratic = np.sum(innovation * innovation, axis=1) + (rhs / variance) ** 2
    # Differencing against one observation removes a fixed-RF c term. The
    # contrast noise determinant includes a factor `count` from the shared first sample.
    baseline = (count - 1) * np.log(PERIOD / (np.sqrt(2 * np.pi) * NOISE)) - .5 * np.log(count)
    return baseline - .5 * (quadratic + np.log(variance))


def score_track(observed, predicted, elevation, phase_derivative, labels, catalogue_size):
    visible = (elevation >= 0).all(axis=1)
    if not np.any(visible) or len(observed) < 2:
        return 0., None
    ratios = contrast_log_ratio(observed, predicted[visible], phase_derivative[visible])
    # Every causal catalogue orbit has the same prior weight, including zero
    # likelihood for invisible candidates. Outlier and orbit-mixture log odds start equal.
    log_odds = np.logaddexp.reduce(ratios) - np.log(catalogue_size)
    owner = int(labels[visible][np.argmax(ratios)]) if log_odds > 0 else None
    return float(np.logaddexp(0, log_odds)), owner


def _prepare_probe_scores(prepared, catalogue, region):
    rows, tracks = prepared["observations"], prepared["tracks"]
    identities = {row["observation_id"]: row["receiver"] for row in rows}
    graph_ids = [i for track in tracks for i in track["observation_ids"]]
    if (not tracks or len(identities) != len(rows) or len(set(graph_ids)) != len(graph_ids)
            or not set(graph_ids) <= identities.keys()):
        raise ValueError("Expected a disjoint Graph subset of the original observations")
    groups = sorted(set(identities.values()))
    counts = {group: sum(r == group for r in identities.values()) for group in groups}
    times = np.unique(np.concatenate([track["times"] for track in tracks]))
    starts = np.unique([track["times"][0] for track in tracks])
    points = list(probes(region))
    metadata = prepared["metadata"]
    locations = [row["latlon"] for row in points]
    geometry, labels = orbit_geometry(catalogue, metadata["anchor_utc_ns"], times, starts,
                                       region.center, locations)
    catalogue_size = len(catalogue.satellite_numbers)
    indexes = [np.searchsorted(times, track["times"]) for track in tracks]

    def score(point):
        sums = dict.fromkeys(groups, 0.)
        owners = dict.fromkeys(t["key"] for t in tracks)
        if geometry is not None:
            frequency, elevation, derivative = phase_linear_frequency(geometry, *point["latlon"])
            for track, indices in zip(tracks, indexes, strict=True):
                q = track["rf_hz"] / 11.5e9
                score, owner = score_track(track["values"], q * frequency[:, indices], elevation[:, indices],
                                           q * derivative[:, indices], labels, catalogue_size)
                sums[track["receiver"]] += score
                owners[track["key"]] = owner
        point.update(score=sum(sums.values()) / len(rows),
                     receiver_scores={str(r): sums[r] / counts[r] for r in groups}, owners=owners)
        return point

    meta = dict(catalogue_orbits=catalogue_size, potentially_visible_orbits=len(labels),
                track_count=len(tracks), graph_points=len(graph_ids), original_points=len(rows),
                receiver_points=counts)
    return points, score, meta


def evaluate(prepared, catalogue, region):
    """Rank new associations at each position with no fitted labels or scoring key."""
    points, score, meta = _prepare_probe_scores(prepared, catalogue, region)
    return dict(points=[score(point) for point in points], **meta)


def evaluate_veto(prepared, catalogue, region):
    """Opt in to the terminal veto on the original all-location geometry."""
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    points, score, meta = _prepare_probe_scores(prepared, catalogue, region)
    decision = evaluate_terminal(points, region.width_km, lambda point: score(point)["receiver_scores"])
    return dict(decision, **meta)


def summarize(points):
    """Use the sign of the pooled gain. Receiver-specific maxima are descriptive."""
    inside, exterior = ([point for point in points if point["side"] == side] for side in RADII)

    def compare(score):
        best_inside = max(inside, key=score)
        best_exterior = max(exterior, key=score)
        gain = score(best_exterior) - score(best_inside)
        return dict(gain=gain, inside=best_inside["xy_km"], exterior=best_exterior["xy_km"])

    pooled = compare(lambda point: point["score"])
    receivers = {r: compare(lambda point: point["receiver_scores"][r]) for r in points[0]["receiver_scores"]}
    return dict(pooled=pooled, receivers=receivers, would_withhold=pooled["gain"] > 0)
