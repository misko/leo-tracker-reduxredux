from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.arm_receiver_eval import chronological, parity


def fixtures():
    return [
        dict(visit=i, counter=200_000 * i, delivery_clock={"monotonic_ns": 20 * i})
        for i in range(6)
    ]


@pytest.mark.parametrize("field", ["visit", "counter", "delivery_clock"])
def test_chronological_fixture_rejects_duplicate_or_reordered_clock(field):
    rows = fixtures()
    chronological(rows)
    rows[2][field] = rows[1][field]
    with pytest.raises(ValueError, match="chronological visits"):
        chronological(rows)


def wave():
    candidate = dict(
        epoch=735,
        coarse_bin=4,
        fractional_epoch=dict(
            status="complete",
            offset_samples=0.2,
            tracking_cfo_hz=-193_450.0,
            exact_score=0.25,
            control_score=0.0,
            margin=0.25,
        ),
    )
    return dict(
        top16=[[735], [735]],
        added_epochs=[3, 3],
        rows=[
            dict(receiver_id=rx, timings_ms={"test": 1.0}, candidates=[deepcopy(candidate)])
            for rx in (0, 1)
        ],
    )


def test_scientific_parity_reports_unequal_float_bytes_and_signed_carrier():
    stock = wave()
    changed = deepcopy(stock)
    changed["rows"][0]["timings_ms"]["test"] = 12.0
    assert parity(stock, changed)["scientific_bytes_agree"]
    changed["rows"][0]["candidates"][0]["fractional_epoch"]["offset_samples"] += 1e-12
    result = parity(stock, changed)
    assert not result["scientific_bytes_agree"]
    assert result["lanes"][0]["ordered_fractional_gates"]
    assert result["lanes"][0]["max_cfo_difference_hz"] == 0
    changed["rows"][0]["candidates"][0]["fractional_epoch"]["tracking_cfo_hz"] *= -1
    assert parity(stock, changed)["lanes"][0]["max_cfo_difference_hz"] == 386_900


def test_equal_region_and_rank_do_not_hide_changed_gate():
    stock = wave()
    changed = deepcopy(stock)
    changed["rows"][1]["candidates"][0]["fractional_epoch"]["margin"] = 0.02
    result = parity(stock, changed)
    assert result["full_ranks_agree"] and result["added_epochs_agree"]
    assert result["lanes"][1]["ordered_integer_keys"]
    assert not result["lanes"][1]["ordered_fractional_gates"]
