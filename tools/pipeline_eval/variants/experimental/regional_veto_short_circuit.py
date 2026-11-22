"""Disprove a far-exterior veto before computing all diagnostic maxima."""

from math import hypot, isfinite

from tools.pipeline_eval.variants.experimental.regional_exterior_veto import PROBES_PER_SIDE, evaluate


def probe_layout(points, width_km):
    """Validate every probe coordinate before requesting any receiver scores."""
    if not isfinite(width_km) or width_km <= 0:
        raise ValueError("Expected a positive offer width")
    sides = {"inside": set(), "exterior": set()}
    eligible, remaining = [], []
    for index, point in enumerate(points):
        x, y = point["xy_km"]
        side = point["side"]
        clearance = max(abs(x), abs(y)) - width_km / 2
        if (not all(map(isfinite, (x, y))) or (side == "inside") != (clearance <= 0)
                or (x, y) in sides[side]):
            raise ValueError("Invalid or duplicate regional probe")
        sides[side].add((x, y))
        target = eligible if side == "exterior" and clearance >= width_km else remaining
        target.append(index)
    if any(len(coordinates) != PROBES_PER_SIDE for coordinates in sides.values()):
        raise ValueError("Incomplete regional probe layout")
    return eligible, remaining


def evaluate_terminal(points, width_km, score_at):
    """Return the stock Boolean and the full readout when every probe is scored."""
    visited = {}
    calls = 0
    receivers = None

    def stopped(reason):
        return dict(would_withhold=False, complete=False, probes_evaluated=calls, stop=reason)

    def inspect(index):
        nonlocal calls, receivers
        calls += 1
        scores = score_at(points[index])
        groups = tuple(sorted(scores))
        if (len(groups) != 2 or (receivers is not None and receivers != groups)
                or not all(map(isfinite, scores.values()))):
            raise ValueError("Invalid receiver scores")
        receivers = groups
        visited[index] = dict(scores)
        return visited[index]

    try:
        points = list(points)
        eligible, remaining = probe_layout(points, width_km)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return stopped("invalid_layout")
    if not eligible:
        return stopped("no_eligible_exterior")

    try:
        for index in eligible:
            inspect(index)
        winners = {r: max(eligible, key=lambda i: visited[i][r]) for r in receivers}
        upper = {r: visited[i][r] for r, i in winners.items()}
        if any(sum(visited[i][r] == limit for i in eligible) > 1 for r, limit in upper.items()):
            return stopped("eligible_exterior_tie")
        first, second = (points[i]["xy_km"] for i in winners.values())
        if hypot(first[0] - second[0], first[1] - second[1]) > width_km:
            return stopped("eligible_exterior_separation")

        for index in remaining:
            scores = inspect(index)
            if any(scores[r] >= limit for r, limit in upper.items()) and calls < len(points):
                side = points[index]["side"]
                return stopped("inside_score" if side == "inside" else "ineligible_exterior_score")
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return stopped("invalid_score")

    scored = [dict(point, receiver_scores=visited[i]) for i, point in enumerate(points)]
    return dict(evaluate(scored, width_km), probes_evaluated=calls)
