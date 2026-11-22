"""Scorer-side geographic sampling for the ALGO08 single-core confirmation."""

from math import cos, radians
import secrets

from tools.pipeline_eval.scoring import distance_km

EDGE_PROTOCOL = "paired-region-edges-v1"
CONTAINING = {"containing", "edge-containing"}
EDGE_CASES = CONTAINING | {"edge-omitted", "far"}
MIN_CENTER_SEPARATION_KM = 1600

# Centers of earlier development simulations and the real DS26/29/30 station.
# The scene generator adds at most two degrees in each coordinate to a center.
DEVELOPMENT_CENTERS = (
    (37.906, -122.545), (48, 15), (-33, 20), (9.5, 76.5), (7.5, -68.5),
    (51, 11), (-23, 30), (-5, -42.5), (54, 10), (-38, 147), (16, -99), (-18, 29),
    (33, -112), (40, -8), (12, 105), (-34, -56), (31, 76), (-32, 147),
    (44, -116), (-37, 175), (2, -55), (-32, 24), (12, 36), (-22, -58),
    (48, -120), (-26, -68), (5, 38), (34, 112), (-39, 169), (54, 32), (-23, -43),
    (58, -93), (-3, 117), (-43, 172), (37, -92), (-44, -70), (30, -7),
    (-31, -54), (44, 93), (-13, 164), (48, -119), (25, 30), (-27, 153),
    (35, 138), (-29, -70), (7, -2), (35, 55), (-15, -63), (33, 138), (-41, -72),
)

# These experiments followed the original seeded waveform generator.
HEIGHT_TRIAL_CENTERS = ((15., 75.), (-25., -65.), (65., 120.))
# City-level exclusion for the UT Austin receiver study, not a surveyed antenna position.
AUSTIN_RECEIVER_AREA = (30.3, -97.7)


def fresh_layout(rng, additional_centers=()):
    """Draw two sites independently of solver outputs, assigning each a pilot edge."""
    excluded = [*DEVELOPMENT_CENTERS, *additional_centers]
    points = []
    sign = int(rng.choice([-1, 1]))
    for direction, band in [(sign, (8, 26)), (-sign, (34, 54))]:
        for _ in range(1000):
            point = (direction * float(rng.uniform(*band)), float(rng.uniform(-172, 172)))
            if all(distance_km(point, old) >= MIN_CENTER_SEPARATION_KM for old in excluded):
                points.append(point)
                excluded.append(point)
                break
        else:
            raise ValueError("Unable to sample a geographically independent site")
    edges = ("lower", "upper") if rng.integers(2) else ("upper", "lower")
    return list(zip(points, edges, strict=True))


def seeded_layout(seed):
    import numpy as np

    return fresh_layout(np.random.default_rng(int.from_bytes(seed, "big")))


def seeded_centers(seed):
    return [center for center, _ in seeded_layout(seed)]


def independent_of_later_trials(centers):
    return all(distance_km(center, used) >= MIN_CENTER_SEPARATION_KM
               for center in centers for used in (*HEIGHT_TRIAL_CENTERS, AUSTIN_RECEIVER_AREA))


def new_confirmation_seed():
    """Draw before synthesizing any signals. Explicit replay seeds stay reproducible."""
    while True:
        seed = secrets.token_bytes(32)
        if independent_of_later_trials(seeded_centers(seed)):
            return seed


def drawn_pilot_edges(seed_hex, sites):
    """Match both revealed sites to the independently drawn boxes and pilot edges."""
    try:
        seed = bytes.fromhex(seed_hex)
    except (TypeError, ValueError):
        return {}
    if len(seed) != 32:
        return {}
    layout = seeded_layout(seed)
    if len(sites) != len(layout) or not independent_of_later_trials([center for center, _ in layout]):
        return {}
    # make_scene jitters each coordinate independently by at most two degrees.
    expected = {tuple(site): edge for center, edge in layout for site in sites
                if abs(site[0] - center[0]) <= 2 and abs(site[1] - center[1]) <= 2}
    return expected if set(expected.values()) == {"lower", "upper"} else {}


def verifies_drawn_sites(seed_hex, sites):
    return bool(drawn_pilot_edges(seed_hex, sites))


def fresh_offers(rng, site):
    """Vary both coordinates and challenge the same face from either side."""
    width = float(rng.uniform(18, 40))
    half = width / 2

    def offer(axis, sign, distance):
        for _ in range(1000):
            along = float(rng.uniform(-.75, .75)) * half
            east, north = (sign * distance, along) if axis == 0 else (along, sign * distance)
            lat = site[0] - north / 111.
            lon = site[1] - east / (111.32 * cos(radians(lat)))
            if lat != site[0] and lon != site[1]:
                return [lat, lon]
        raise ValueError("Could not draw an offer that varies both receiver coordinates")

    def face():
        return int(rng.integers(2)), int(rng.choice([-1, 1]))

    edge = face()
    return width, {
        "containing": offer(*face(), half * rng.uniform(.15, .8)),
        "edge-containing": offer(*edge, half - rng.uniform(.05, .25)),
        "edge-omitted": offer(*edge, half + rng.uniform(.05, .25)),
        "far": offer(*face(), half * rng.uniform(2.5, 5.5)),
    }
