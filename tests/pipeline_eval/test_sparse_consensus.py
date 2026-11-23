from reports.ALGO08.v3.sparse_consensus import buffered, choose, paid_visits


def test_future_support_and_signed_slope_limits():
    assert choose([100_000, -12_000], [(t, [-12_000 - 450 * t]) for t in (1, 2, 3)]) == 1
    assert choose([0], [(t, [9000 * t]) for t in (1, 2, 3)]) is None
    assert choose([0], [(1, [1, 2, 3])]) is None
    assert choose([0], [(t, [0]) for t in (.01, .02, .03)]) is None


def test_mask_stereo_and_no_cross_lane_evidence():
    rows = [dict(channel=i % 2, actual_rf_hz=i % 2, edge="upper", receiver_id=rx,
                 visit_index=i, valid_start_counter=i * 100,
                 candidates=[{"fractional_tracking_cfo_hz": 10}]) for i in range(24) for rx in (0, 1)]
    paid = paid_visits(rows)
    assert paid == {0, 6, 12, 18, 3, 9, 15, 21}
    assert sum(map(bool, buffered(rows, paid, 1000))) == 16
    for row in rows:
        if row["visit_index"] not in paid:
            row["candidates"] = [None]
        elif row["receiver_id"] == 1 and row["visit_index"] != 0:
            row["candidates"] = []
    result = buffered(rows, paid, 1000)
    assert not any(result[1::2])
    assert sum(map(bool, result)) == 8
    assert not any(buffered(rows, paid, 1))
