from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.tail_position import GATE, bind_lane, selection, tally


def test_anchors_and_empty_lanes_do_not_take_tail_scores():
    assert selection("full", True, False, None) == (True, True)
    assert selection("short_primary", False, False, None) == (False, False)
    with pytest.raises(ValueError, match="full anchor or empty lane"):
        selection("full", True, True, (.6, 0.))
    with pytest.raises(ValueError, match="missing its measured tail"):
        selection("short_primary", True, True, None)


def test_selective_rescue_preserves_original_history_support_and_fixed_gate():
    assert selection("short_primary", True, True, (0., 0.)) == (True, False)
    assert selection("short_primary", True, False, (GATE, 0.)) == (True, True)
    assert selection("short_primary", True, False, (0., GATE)) == (False, False)
    rows = [dict(mode=mode, positive=True, lane=lane, causal=causal, selective=selective, all=all_pass)
            for mode, lane, causal, selective, all_pass in
            (("full", 0, False, True, True), ("short_primary", 0, True, True, False),
             ("short_primary", 1, False, True, True), ("short_primary", 1, False, False, False))]
    counts = tally(rows)
    assert counts["both"]["causal_omitted"] == 2
    assert counts["both"]["causal_omitted_rescued"] == 1
    assert counts["0"]["full_selective"] == 1
    assert counts["0"]["causal_kept_lost_by_all"] == 1
    assert counts["1"]["short_primary_selective"] == 1


def test_signed_lane_binds_hardware_counter_and_receiver():
    item = SimpleNamespace(acquisition=dict(global_visit=20, sample_start=90000, actual_if_center_hz=100),
                           target=dict(edge="upper", channel=3, lnb_lo_hz=2000))
    base = dict(visit_index=20, receiver_id=0, valid_start_counter=90000, edge="upper", channel=3,
                actual_rf_hz=2100, candidates=[dict(passed_fractional_margin_gate=True)])
    bind_lane(item, base, 0)
    for field, value in (("valid_start_counter", 90001), ("actual_rf_hz", 2101), ("receiver_id", 1),
                         ("candidates", [dict(passed_fractional_margin_gate=False)])):
        with pytest.raises(ValueError, match="signed factor"):
            bind_lane(item, dict(base, **{field: value}), 0)
