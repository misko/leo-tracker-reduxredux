from math import remainder

import pytest

from reports.ALGO08.v3.empty_graph_outer_donors import (
    ADC, HERTZ, PERIOD, equal_count_hash, evaluate_donors, measure, side_at,
)


CENTER = 2**54 + 1


def lane(oid, t, hz, phase, *, lift=0, receiver=0):
    counter = CENTER + round(t * ADC)
    offset = (phase - (3 * counter % 40_000) / 3) % PERIOD
    return dict(id=oid, counter=counter, lift=lift,
                row=dict(edge="upper", channel=2, actual_rf_hz=1000, receiver_id=receiver),
                factor={HERTZ: hz, "integer_epoch_sample": int(offset),
                        "fractional_epoch_offset_samples": offset - int(offset)})


def quartet():
    return [lane(chr(97 + i), t, -500 + 300*t, 125*t) for i, t in enumerate((-3, -1, .5, 2))]


def test_independent_extrapolation_preserves_modular_arrival_and_signed_cfo():
    result, why = evaluate_donors(lane("target", 0, 0, 0), 1, 2, quartet())
    assert why is None
    assert result["donor_ids"] == ["a", "b", "c", "d"]
    assert result["left"]["signed_cfo_hz"] == result["right"]["signed_cfo_hz"] == -500
    assert remainder(result["left"]["phase_samples"], PERIOD) == pytest.approx(0.)
    assert remainder(result["right"]["phase_samples"], PERIOD) == pytest.approx(0.)
    assert result["arrival_gap_samples"] == pytest.approx(0.)
    assert result["outer_future_delay_s"] == 2


@pytest.mark.parametrize(("change", "reason"), [
    (dict(t=4.0001, hz=100, phase=250), "outer_spacing"),
    (dict(t=2, hz=100, phase=250, receiver=1), "different_lane"),
    (dict(t=2, hz=100, phase=250, lift=1), "different_lifts"),
    (dict(t=2, hz=100, phase=280), "arrival_disagrees"),
    (dict(t=2, hz=8_100, phase=250), "carrier_disagrees"),
    (dict(t=2, hz=90_000, phase=250), "carrier_rate"),
    (dict(t=2, hz=100, phase=4_250), "phase_rate"),
    (dict(t=2, hz=float("nan"), phase=250), "nonfinite"),
])
def test_fail_closed_for_out_of_scope_or_inconsistent_donors(change, reason):
    rows = quartet()
    rows[-1] = lane("d", **change)
    assert evaluate_donors(lane("target", 0, 0, 0), 1, 2, rows) == (None, reason)


def test_no_skipping_missing_or_crossed_neighbors():
    rows = quartet()
    target = lane("target", 0, 0, 0)
    assert evaluate_donors(target, 0, 1, rows[1:]) == (None, "missing_outer_donor")
    with pytest.raises(ValueError, match="consecutive"):
        evaluate_donors(target, 0, 2, rows)
    with pytest.raises(ValueError, match="same strict side"):
        side_at(rows[1], rows[2], target["counter"])


def test_hash_control_matches_count_and_uses_fixed_order():
    query = ["a", "b", "c", "d"]
    assert equal_count_hash(query, 2) == equal_count_hash(reversed(query), 2)
    assert equal_count_hash(query, 2) == equal_count_hash(query, 4)[:2]
    assert len(set(equal_count_hash(query, 2))) == 2
    assert equal_count_hash(query, 0) == []


def test_unchanged_interpolated_query_and_all_positive_denominator():
    stock = {"hit": lane("hit", 0, -500, 2), "omitted": lane("omitted", 0, 5, 10),
             "empty": dict(factor=None)}
    proposal = dict(centers_hz=[-500.], phase=dict(interpolated=2., left_only=100.,
                                                   quarter_period_control=100.))
    ownership = {"c0": {"hit": 1}, "fitted_c": {"omitted": 1}}
    covered = measure(["hit", "empty"], set(stock), {"hit": proposal, "empty": proposal}, stock, ownership)
    assert covered["installed_empty_queries"] == 1
    assert covered["whole_scope"]["installed_positive_denominator"] == 2
    assert covered["whole_scope"]["windows"]["primary"]["interpolated"] == 1
    assert covered["exact_owner_scope"]["c0"]["owned"]["windows"]["primary"]["interpolated"] == 1
    assert covered["exact_owner_scope"]["fitted_c"]["owned"]["installed_positive_denominator"] == 1
    assert covered["exact_owner_scope"]["fitted_c"]["nonowned"]["windows"]["primary"]["interpolated"] == 1
