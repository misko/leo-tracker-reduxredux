import pytest

from reports.ALGO08.v3 import held_cfo_innovation as check


def lane(hz, arrival=0, short=True):
    factor = None if hz is None else {
        check.odd.HERTZ: hz,
        "integer_epoch_sample": arrival,
        "fractional_epoch_offset_samples": 0.,
    }
    return dict(counter=2**54, short=short, factor=factor)


def test_residual_gate_uses_only_positive_held_slots_and_strict_250_hz():
    held = dict.fromkeys(("edge", "flag", "measured_empty", "no_forecast"))
    original = {"edge": lane(250), "flag": lane(-251), "measured_empty": lane(None), "no_forecast": lane(0)}
    proposals = {oid: dict(cfo_hz=0.) for oid in ("edge", "flag", "measured_empty")}
    keys, plan = check.select(held, proposals, original)
    assert keys == {"edge", "flag", "no_forecast"}
    assert plan["absolute_innovation_hz"] == {"edge": 250., "flag": 251.}
    assert plan["selected"] == ["flag"]
    assert len(plan["equal_count_hash"]) == 1
    assert check.select(dict(reversed(list(held.items()))), proposals, original)[1] == plan
    with pytest.raises(ValueError, match="Only pre-masked"):
        check.select({"edge": None}, proposals, original)
    with pytest.raises(ValueError, match="all be short"):
        check.select(held, proposals, dict(original, edge=lane(250, short=False)))


def test_signed_cfo_and_delay_only_failures_have_distinct_effects():
    original = {"cfo": lane(500), "delay": lane(0, 10), "empty": lane(500),
                "spoiled": lane(0), "wrong_and_late": lane(600, 8)}
    stock = dict.fromkeys(original, lane(0)) | {"empty": lane(None)}
    arrival = check.arrival_phase(stock["cfo"]["counter"],stock["cfo"]["factor"])
    forecasts = {oid: dict(cfo_hz=0., arrival=arrival) for oid in original}
    forecasts["spoiled"]["cfo_hz"] = 500
    errors = check.original_errors(original, original, stock)
    counts = check.evaluate(original, forecasts, errors, original, stock)
    assert counts["original_categories"] == dict(installed_empty=1, wrong_cfo=2, delay_only=1, original_strict_hit=1)
    assert counts["wrong_cfo_closer"] == counts["cfo_restored"] == 2
    assert counts["closer"] == 2 and counts["farther"] == 1 and counts["equal"] == 1
    assert counts["cfo_spoiled"] == counts["strict_spoiled_keep_arrival"] == 1
    assert counts["strict_restored_keep_arrival"] == 1
    assert counts["strict_restored_forecast_arrival"] == 3


def test_continuation_requires_informative_counts_and_all_comparative_gates():
    gate = dict(queries=12, original_categories=dict(installed_empty=1, wrong_cfo=6), cfo_restored=4,
                strict_restored_keep_arrival=3, strict_spoiled_keep_arrival=1)
    other = dict(gate, original_categories=dict(wrong_cfo=3), cfo_restored=2)
    case = dict(eligible_categories=dict(wrong_cfo=10), corrections=dict(innovation=gate,equal_count_hash=other))
    assert check.continuation(case) == "extend_positive"
    other["cfo_restored"] = 4
    assert check.continuation(case) == "stop"
    case["eligible_categories"]["wrong_cfo"] = 9
    assert check.continuation(case) == "extend_sparse"
