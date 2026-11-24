from copy import deepcopy

from reports.ALGO08.v3.ds30_0163_composed_saved import own_endpoint_scores, route_signature


def test_route_signature_checks_decisions_and_excludes_clock():
    route = {"solves": [{
        "choice": {"route": "lean", "reason": "healthy_samples", "cpu_ns": 100},
        "lean_attempts": [{"decision": "complete", "cold": {"routing": "fit", "branch": 1}}],
        "nomination_handoff": {"geometry_guard_cpu_ns": 1000, "speculative_ranks_excluded": 1},
        "two_centre_rank": {"ranked_nodes": 3, "distinct_finalists": 3, "paid_centres": 2},
        "lean_final_fit": {},
        "inference_calls": 1,
    }]}
    other = deepcopy(route)
    other["solves"][0]["nomination_handoff"]["geometry_guard_cpu_ns"] = 2000
    assert route_signature(route) == route_signature(other)
    other["solves"][0]["lean_attempts"][0]["cold"]["branch"] = 2
    assert route_signature(route) != route_signature(other)


def test_grid_uses_each_arms_own_terminal_coordinate():
    grid = {"endpoints": {"c0": [0.0, 0.0], "fitted_c": [1.0, 1.0]}, "points": [
        {"east_km": 1.0, "north_km": 1.0, "scores": {"c0": 3.0, "fitted_c": 2.0}},
        {"east_km": 0.0, "north_km": 0.0, "scores": {"c0": 1.0, "fitted_c": 4.0}},
    ]}
    assert own_endpoint_scores(grid) == {"c0": (1.0).hex(), "fitted_c": (2.0).hex()}
