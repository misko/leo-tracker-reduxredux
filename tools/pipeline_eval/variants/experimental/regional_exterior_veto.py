"""Apply a predeclared two-receiver veto to complete regional probe scores."""

from math import hypot, isfinite


PROBES_PER_SIDE = 48


def evaluate(points, width_km):
    """Use each receiver's independent best inside and exterior evaluations."""
    incomplete = dict(would_withhold=False, complete=False)
    by_side = {"inside": {}, "exterior": {}}
    receivers = None
    try:
        if not isfinite(width_km) or width_km <= 0:
            return incomplete
        for point in points:
            x, y = point["xy_km"]
            scores = point["receiver_scores"]
            side = point["side"]
            clearance = max(abs(x), abs(y)) - width_km / 2
            receiver_ids = set(scores)
            if (
                not all(map(isfinite, (x, y))) or len(receiver_ids) != 2
                or (receivers is not None and receivers != receiver_ids)
                or not all(map(isfinite, scores.values()))
                or (side == "inside") != (clearance <= 0)
                or (x, y) in by_side[side]
            ):
                return incomplete
            receivers = receiver_ids
            by_side[side][x, y] = scores
    except (AttributeError, KeyError, TypeError, ValueError):
        return incomplete
    inside, exterior = by_side["inside"], by_side["exterior"]
    if len(inside) != PROBES_PER_SIDE or len(exterior) != PROBES_PER_SIDE:
        return incomplete

    best = {}
    for receiver in sorted(receivers):
        inside_xy = max(inside, key=lambda xy: inside[xy][receiver])
        exterior_xy = max(exterior, key=lambda xy: exterior[xy][receiver])
        inside_score = inside[inside_xy][receiver]
        exterior_score = exterior[exterior_xy][receiver]
        maxima = sum(scores[receiver] == exterior_score for scores in exterior.values())
        best[receiver] = dict(
            gain=exterior_score - inside_score,
            inside_xy_km=inside_xy,
            exterior_xy_km=exterior_xy,
            exterior_clearance_km=max(map(abs, exterior_xy)) - width_km / 2,
            unique_exterior=maxima == 1,
        )
    first, second = (record["exterior_xy_km"] for record in best.values())
    separation = hypot(first[0] - second[0], first[1] - second[1])
    withhold = separation <= width_km and all(
        row["unique_exterior"] and row["gain"] > 0 and row["exterior_clearance_km"] >= width_km
        for row in best.values()
    )
    return dict(would_withhold=withhold, complete=True, receivers=best,
                exterior_separation_km=separation)
