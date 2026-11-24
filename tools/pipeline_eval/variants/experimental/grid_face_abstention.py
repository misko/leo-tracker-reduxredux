"""Read competitive sampled face contact from an existing paired loss map."""

from math import isfinite, log

from leo.analysis.position_grid import ARMS

LEVEL = -2 * log(0.05)
FACES = (("west", 0, -1), ("east", 0, 1), ("south", 1, -1), ("north", 1, 1))


def face_contact(grid):
    """Return per-arm face witnesses using the unchanged, common grid points."""
    if not grid or grid.get("complete") is not True or grid.get("matched_c_grid") is not True:
        return {"state": "unassessable", "reason": "incomplete_paired_grid"}
    half = grid["box_width_km"] / 2
    points = {
        (row["east_km"], row["north_km"]): row["scores"] for row in grid["points"]
    }
    if (
        not isfinite(half) or half <= 0 or len(points) != len(grid["points"])
        or any(max(map(abs, xy)) > half or not all(map(isfinite, xy)) for xy in points)
        or any(set(scores) != set(ARMS) or any(v is None or not isfinite(v) for v in scores.values())
               for scores in points.values())
    ):
        return {"state": "unassessable", "reason": "invalid_paired_scores"}

    by_face = {name: [xy for xy in points if xy[axis] == sign * half]
               for name, axis, sign in FACES}
    if not all(by_face.values()):
        return {"state": "unassessable", "reason": "unsampled_face"}
    endpoints = {arm: tuple(grid["endpoints"][arm]) for arm in ARMS}
    if any(xy not in points for xy in endpoints.values()):
        return {"state": "unassessable", "reason": "unsampled_endpoint"}

    arms = {}
    for arm, endpoint in endpoints.items():
        all_best = min(points, key=lambda xy: points[xy][arm])
        inside_loss = points[all_best][arm]
        faces = {}
        for name, axis, sign in FACES:
            face_points = by_face[name]
            best = min(face_points, key=lambda xy: points[xy][arm])
            nearest = min(abs(xy[1 - axis] - endpoint[1 - axis]) for xy in face_points)
            faces[name] = {
                "best_face_xy_km": best, "gap": points[best][arm] - inside_loss,
                "endpoint_clearance_km": half - sign * endpoint[axis],
                "nearest_tangent_offset_km": nearest, "samples": len(face_points),
            }
        best_face = min(faces, key=lambda name: faces[name]["gap"])
        gap = faces[best_face]["gap"]
        arms[arm] = {
            "gap": gap, "face": best_face, "faces": faces, "minimum_xy_km": all_best,
            "minimum_score": inside_loss, "endpoint_loss_gap": points[endpoint][arm] - inside_loss,
            "endpoint_xy_km": endpoint, "contact": gap <= LEVEL,
        }
    gaps = [arm["gap"] for arm in arms.values()]
    return {
        "state": "assessable", "arms": arms, "paired_gap": min(gaps), "both_gap": max(gaps),
        "paired_abstain": min(gaps) <= LEVEL, "both_abstain": max(gaps) <= LEVEL,
    }


def separating_interval(kept, omitted):
    """All thresholds retaining every containing case and abstaining on the omissions."""
    lower, upper = max(omitted), min(kept)
    return {"lower_inclusive": lower, "upper_exclusive": upper, "exists": lower < upper}
