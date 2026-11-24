from reports.ALGO08.v3.exact_named_south_omitted import observe_boundary


def test_boundary_observer_preserves_inactive_decision_and_both_coordinates():
    endpoints = {"c0": (12.27, -0.31), "fitted_c": (12.24, -0.58)}
    expected = {"bound_arms": [], "evaluated": False, "would_withhold": False}

    def score():
        raise AssertionError("Inactive candidate must not pay exterior probes")

    def inspect(points, width, probe, *, terminal_only=False):
        assert points == endpoints and width == 25.0 and probe is score and terminal_only
        return expected

    proof = []
    result = observe_boundary(inspect, proof)(endpoints, 25.0, score, terminal_only=True)
    assert result is expected
    assert proof == [{"width_km": 25.0, "endpoints_east_north_km": endpoints, **expected}]


def test_boundary_observer_forwards_exterior_probe_evidence():
    endpoints = {"c0": (12.5, 0.1), "fitted_c": (12.48, 0.0)}
    evidence = {"bound_arms": ["c0"], "evaluated": True, "would_withhold": True, "probes_evaluated": 110}

    def inspect(points, width, score, *, terminal_only):
        assert terminal_only
        return score()

    proof = []
    result = observe_boundary(inspect, proof)(endpoints, 25.0, lambda: evidence, terminal_only=True)
    assert result is evidence and proof[0]["probes_evaluated"] == 110
