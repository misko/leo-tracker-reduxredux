import prototype_mixture_position as prototype


def test_clock_endpoint_propagation_uses_receiver_clock_keyword(monkeypatch) -> None:
    observed = {}

    def fake_state_arrays(cat, indices, reference_utc_ns, time_s, orbit_time_s=0.0, *, clock_s=0.0):
        observed.update(orbit_time_s=orbit_time_s, clock_s=clock_s)
        return "p", "v", "valid"

    monkeypatch.setattr(prototype, "state_arrays", fake_state_arrays)
    result = prototype.clock_endpoint_states("cat", [0], 123, [1.0, 2.0], -0.5)
    assert result == ("p", "v", "valid")
    assert observed == {"orbit_time_s": 0.0, "clock_s": -0.5}
