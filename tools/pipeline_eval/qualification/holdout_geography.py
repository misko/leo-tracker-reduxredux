"""Scorer-side geographic sampling for the ALGO08 single-core confirmation."""

from tools.pipeline_eval.scoring import distance_km


# Centers of earlier development simulations and the real DS26/29/30 station.
# The scene generator adds at most two degrees in each coordinate to a center.
DEVELOPMENT_CENTERS = (
    (37.906, -122.545), (48, 15), (-33, 20), (9.5, 76.5), (7.5, -68.5),
    (51, 11), (-23, 30), (-5, -42.5), (54, 10), (-38, 147), (16, -99), (-18, 29),
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
