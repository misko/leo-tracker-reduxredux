from reports.ALGO08.v3.cross_lag_eight_ms import RULE, anchor_lanes


def test_each_signed_stream_and_antenna_keeps_its_original_full_anchor_cycle():
    rows = [dict(visit_index=visit, receiver_id=lane, channel=channel, edge="lower", actual_rf_hz=rf)
            for visit in range(9) for channel, rf in ((1, 1.), (2, 2.)) for lane in (0, 1)]
    anchors = list(anchor_lanes(rows))
    assert len(anchors) == 8
    assert {row["visit_index"] for row in anchors} == {0, 8}
    assert {row["receiver_id"] for row in anchors} == {0, 1}
    assert RULE == (1666, 1.1)
