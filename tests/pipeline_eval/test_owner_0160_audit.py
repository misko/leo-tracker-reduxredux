import pytest

from reports.ALGO08.v3.owner_0160_audit import observations, owners, summaries, transitions


def test_owner_transitions_count_role_and_satellite_changes_independently():
    old = owners([("same", 1, "conditional"), ("gone", 2, "conditional"),
                  ("changed", 3, "predictive"), ("role", 5, "conditional")])
    new = owners([("same", 1, "conditional"), ("new", 2, "predictive"),
                  ("changed", 4, "conditional"), ("role", 5, "predictive")])
    assert transitions(old, new) == dict(removed=["gone"], added=["new"], owner_switch=["changed"],
                                         role_switch=["changed", "role"], unchanged=["same"])
    with pytest.raises(ValueError, match="Ambiguous"):
        owners([("a", 2, "conditional"), ("a", 4, "predictive")])


def test_observation_support_uses_signed_frequency_native_counter_and_radio_mapping():
    same_mark = dict(fractional_margin=.13, passed_fractional_margin_gate=True)
    candidate = dict(same_mark, fractional_tracking_cfo_hz=-2431., candidate_rank=0)
    other = dict(same_mark, fractional_tracking_cfo_hz=3500., candidate_rank=1)
    empty = dict(receiver_id=0, candidates=[])
    measured = dict(receiver_id=1, candidates=[other, candidate], actual_rf_hz=10_940_312_500.,
                    valid_start_counter=75_000_100, channel=1, visit_index=37)
    native = dict(source=dict(probes=[empty, measured], session_id="session", sample_rate_hz=10_000_000,
                              probe_ms=20), clock_anchor=dict(sample_counter=100))
    joined = observations(native)
    assert len(joined) == 1
    identity, = joined
    assert joined[identity]["receiver"] == 2
    assert joined[identity]["native_receiver_id"] == 1
    assert joined[identity]["time_s"] == 7.51
    assert joined[identity]["signed_cfo_hz"] == -2431.
    grouped, = summaries({identity: (57781, "predictive")}, joined)
    assert grouped["time_s"] == [7.51, 7.51]
    assert grouped["signed_cfo_hz"] == [-2431., -2431.]
