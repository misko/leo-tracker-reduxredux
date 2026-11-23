"""Test a clipped face for sustained and competing-interior-checked exterior gain."""

from math import inf, isfinite, nextafter

from tools.pipeline_eval.variants.experimental.regional_bound_guard import (
    ARMS,
    bound_arms,
)
from tools.pipeline_eval.variants.experimental.regional_reassignment import RADII
from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import (
    probe_layout,
)


def shared_face(endpoints, width_km):
    if bound_arms(endpoints, width_km) != list(ARMS):
        return None
    limit = nextafter(width_km / 2, -inf)
    faces = [
        (axis, sign) for axis in (0, 1) for sign in (-1, 1)
        if all(sign * endpoints[arm][axis] >= limit for arm in ARMS)
    ]
    if len(faces) != 1:
        return None
    axis, sign = faces[0]
    if any(abs(endpoints[arm][1 - axis]) >= limit for arm in ARMS):
        return None
    return axis, sign


def evaluate(endpoints, width_km, points, score_at):
    """Use a shared caller cache to reuse original geometry and receiver scores."""
    face = shared_face(endpoints, width_km)
    ray_results = []
    visited = {}

    def result(stop, witness=None):
        return {
            "would_withhold": stop == "exterior_supported", "stop": stop, "face": face,
            "probes_evaluated": len(visited), "rays": ray_results, "witness": witness,
        }

    if face is None:
        return result("no_shared_face")
    points = list(points)
    try:
        probe_layout(points, width_km)
        axis, sign = face
        radii = (*RADII["inside"][-2:], *RADII["exterior"][:2])
        rows = {}
        for point in points:
            xy = tuple(point["xy_km"])
            rows[sign * xy[axis], xy[1 - axis]] = point
        normal = tuple(r * width_km for r in radii)
        tangents = sorted(y for x, y in rows if x == normal[1])
        rays = [[rows[x, tangent] for x in normal] for tangent in tangents]
        if len(rays) != 3:
            raise ValueError("Expected three sampled rays on the shared face")
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return result("invalid_layout")

    groups = None

    def score(point):
        nonlocal groups
        xy = tuple(point["xy_km"])
        if xy not in visited:
            scores = score_at(point)
            verified = tuple(sorted(scores))
            if (
                len(verified) != 2 or (groups is not None and groups != verified)
                or not all(map(isfinite, scores.values()))
            ):
                raise ValueError("Expected two finite causal receiver scores")
            groups = verified
            visited[xy] = dict(scores)
        return visited[xy]

    def strictly_better(exterior, interior):
        return all(exterior[rx] > interior[rx] for rx in groups)

    candidates = {}
    try:
        for wide_in, near_in, near_out, wide_out in rays:
            low, high = score(near_in), score(near_out)
            ray = {
                "near_in": near_in["xy_km"], "near_out": near_out["xy_km"],
                "face_gain": {rx: high[rx] - low[rx] for rx in groups},
            }
            ray_results.append(ray)
            if not strictly_better(high, low):
                continue
            inside, outside = score(wide_in), score(wide_out)
            ray.update(
                inner_gain={rx: low[rx] - inside[rx] for rx in groups},
                outer_gain={rx: outside[rx] - high[rx] for rx in groups},
            )
            if strictly_better(low, inside) and strictly_better(outside, high):
                candidates[tuple(wide_out["xy_km"])] = outside
        if not candidates:
            return result("no_outward_rise")
        best_inside = dict.fromkeys(groups, -inf)
        for point in points:
            if point["side"] != "inside":
                continue
            interior = score(point)
            candidates = {xy: v for xy, v in candidates.items() if strictly_better(v, interior)}
            if not candidates:
                return result("viable_interior", {"xy_km": point["xy_km"], "scores": interior})
            for rx, value in interior.items():
                best_inside[rx] = max(best_inside[rx], value)
    except (AttributeError, KeyError, OSError, TypeError, ValueError, OverflowError):
        return result("unavailable_score")

    def margin(xy):
        return min(candidates[xy][rx] - best_inside[rx] for rx in groups)

    winner = max(candidates, key=margin)
    return result("exterior_supported", {
        "xy_km": winner, "gain": {rx: candidates[winner][rx] - best_inside[rx] for rx in groups},
        "inside_maximum": best_inside,
    })
