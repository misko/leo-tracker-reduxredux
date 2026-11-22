"""Scorer-side geographic sampling for the ALGO08 single-core confirmation."""

from math import cos, radians

from tools.pipeline_eval.scoring import distance_km

EDGE_PROTOCOL = "paired-region-edges-v1"
CONTAINING = {"containing", "edge-containing"}
EDGE_CASES = CONTAINING | {"edge-omitted", "far"}

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


def fresh_layout(rng, additional_centers=()):
    """Draw two sites independently of solver outputs, assigning each a pilot edge."""
    excluded = [*DEVELOPMENT_CENTERS, *additional_centers]
    points = []
    sign = int(rng.choice([-1, 1]))
    for direction, band in [(sign, (8, 26)), (-sign, (34, 54))]:
        for _ in range(1000):
            point = (direction * float(rng.uniform(*band)), float(rng.uniform(-172, 172)))
            if all(distance_km(point, old) >= 1600 for old in excluded):
                points.append(point)
                excluded.append(point)
                break
        else:
            raise ValueError("Unable to sample a geographically independent site")
    edges = ("lower", "upper") if rng.integers(2) else ("upper", "lower")
    return list(zip(points, edges, strict=True))


def fresh_offers(rng, site):
    """Vary both coordinates and challenge the same face from either side."""
    width = float(rng.uniform(18, 40))
    half = width / 2

    def offer(axis, sign, distance):
        along = float(rng.uniform(-.75, .75)) * half
        east, north = (sign * distance, along) if axis == 0 else (along, sign * distance)
        lat = site[0] - north / 111.
        return [lat, site[1] - east / (111.32 * cos(radians(lat)))]

    def face():
        return int(rng.integers(2)), int(rng.choice([-1, 1]))

    edge = face()
    return width, {
        "containing": offer(*face(), half * rng.uniform(.15, .8)),
        "edge-containing": offer(*edge, half - rng.uniform(.05, .25)),
        "edge-omitted": offer(*edge, half + rng.uniform(.05, .25)),
        "far": offer(*face(), half * rng.uniform(2.5, 5.5)),
    }
