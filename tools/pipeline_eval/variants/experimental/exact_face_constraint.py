"""Read a shared active geographic constraint from saved optimizer endpoints."""

from math import inf, nextafter

from tools.pipeline_eval.variants.experimental.regional_bound_guard import ARMS, bound_arms

FACES = (("west", 0, -1), ("east", 0, 1), ("south", 1, -1), ("north", 1, 1))


def diagnose(status, width_km, endpoints):
    """Only a published fix with overlapping active sets changes decision."""
    if status != "complete":
        return {"state": "unchanged", "outcome": status}
    if endpoints is None or bound_arms(endpoints, width_km) is None:
        return {"state": "unassessable", "outcome": status}
    half = width_km / 2
    limit = nextafter(half, -inf)
    arms = {
        arm: {
            "active_faces": [face for face, axis, sign in FACES
                             if sign * endpoints[arm][axis] >= limit],
            "nearest_clearance_km": half - max(map(abs, endpoints[arm])),
        }
        for arm in ARMS
    }
    first, second = (arms[arm]["active_faces"] for arm in ARMS)
    shared = [face for face in first if face in second]
    return {"state": "assessable", "outcome": "withheld" if shared else status,
            "arms": arms, "shared_faces": shared}
