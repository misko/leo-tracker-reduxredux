import pytest

from reports.ALGO08.v3.weak_all8_adaptive import budget, receive_tails


def test_reused_index_ratio_and_first_use_remain_separate():
    timing = budget(12.8, 3., 5.3, 2.)
    assert timing["target_1p6_elapsed_s"] == 8.
    assert timing["saved_allowance_s"] == 5.
    assert timing["separate_clock_total_s"] == pytest.approx(8.3)
    assert timing["target_gap_s"] == pytest.approx(0.3)
    assert timing["optional_serial_first_use_sum_s"] == pytest.approx(10.3)
    assert timing["modeled_ratio"] < 1.6


def scenario(cfo, tuning=11.5e9):
    rows = []
    for i, row in enumerate(cfo):
        candidates = [] if row is None else [dict(fractional_tracking_cfo_hz=row, passed_fractional_margin_gate=True,
                                                  fractional_margin=1., candidate_rank=0)]
        rows.append(dict(receiver_id=i % 2, valid_start_counter=i, channel=1, actual_rf_hz=tuning,
                         edge="lower", candidates=candidates))
    return dict(source=dict(probes=rows))


def test_tails_use_genuine_common_native_opportunities_and_null_if_empty():
    old = scenario([5., None, 10., 10.])
    new = scenario([0., 8., 410., None])
    scores = receive_tails(old, new)
    assert scores["0"]["common"] == 2 and scores["0"]["beyond_250_hz"] == 1
    assert scores["0"]["max_abs_cfo_delta_hz"] == 400.
    assert scores["1"]["common"] == 0 and scores["1"]["p95_abs_cfo_delta_hz"] is None
    with pytest.raises(ValueError, match="identical native lane"):
        receive_tails(old, scenario([0., 8., 410., None], tuning=11.3e9))
