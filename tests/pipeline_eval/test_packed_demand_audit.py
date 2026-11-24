import pytest

from reports.ALGO08.v3.packed_demand_audit import demand


RULE = ["full"] + ["short_primary"] * 7


def fixture():
    rows = [dict(visit_index=visit, receiver_id=lane, edge="lower", channel=channel, actual_rf_hz=1_000,
                 candidates=[dict(passed_fractional_margin_gate=True)] if visit in (0, 2) else [])
            for visit, channel in ((0, 1), (2, 1), (3, 2), (4, 2)) for lane in (0, 1)]
    blocks = [dict(sequence=visit, parts=[[0, 50 + visit], [0, 32 + visit]]) for visit in range(5)]
    return rows, blocks


def test_two_paid_antenna_lanes_share_one_extra_tail():
    probes, records = fixture()
    result = demand(probes, [(2, 0), (2, 1)], records, RULE)
    assert result["full_visits"] == [0, 3]
    assert result["paid_visits"] == [2]
    assert result["invalid_visits"] == [1]
    assert result["earlier_unrefined"]["tail_blocks"] == 2
    assert result["combined_demand"] == dict(prefix_blocks=4, tail_blocks=3,
                                              decoded_bytes=5_760_000, encoded_payload_bytes=310)


def test_invalid_paid_attempts_and_nonconsecutive_committed_rows_stop():
    probes, records = fixture()
    for paid in ([(0, 0)], [(4, 0)], [(2, 0), (2, 0)], [(2, 2)]):
        with pytest.raises(ValueError, match="paid CFO"):
            demand(probes, paid, records, RULE)
    with pytest.raises(ValueError, match="ordered member"):
        demand(probes, [], records[::-1], RULE)
