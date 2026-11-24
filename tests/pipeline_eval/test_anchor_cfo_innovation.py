"""Test the causal signed-CFO diagnostic on synthetic saved-row shapes."""

import pytest

from reports.ALGO08.v3.anchor_cfo_innovation import (
    ALIAS, HERTZ, SAMPLE_RATE, compare_errors, infer_offsets, paired_measurements,
)


def lane(t, hz, *, short=True, rank=0, epoch=0, radio=0):
    factor = None if hz is None else {HERTZ: hz, "candidate_rank": rank,
                                     "integer_epoch_sample": epoch, "fractional_epoch_offset_samples": 0.}
    return dict(counter=int(SAMPLE_RATE*t), short=short, factor=factor,
                row=dict(receiver_id=radio, edge="upper", channel=3, actual_rf_hz=11_100_000_000,
                         candidates=[] if factor is None else [factor]))


def test_past_short_prediction_at_full_anchor_does_not_feed_the_correction_back():
    first = {"a": lane(0., -1_000.), "b": lane(.5, -900.), "c": lane(1., -800.),
             "anchor": lane(1.5, -600., short=False), "target": lane(2., -600.)}
    prefix = infer_offsets(first)
    assert prefix["anchor_innovations_hz"] == {"anchor": 100.}
    assert prefix["short_offsets"] == {"target": [50., "anchor"]}
    extended = dict(first, next=lane(2.5, -500.), other_radio=lane(2.5, -500., radio=1),
                    reset=lane(3., None, short=False), after_reset=lane(3.5, -300.))
    assert infer_offsets(extended)["short_offsets"] == {"target": [50., "anchor"], "next": [50., "anchor"]}


def test_rank_one_anchor_and_stale_or_outlying_short_cannot_receive_offset():
    first = {"a": lane(0., -1_000.), "b": lane(.5, -900.), "c": lane(1., -800.)}
    assert infer_offsets(dict(first, anchor=lane(1.5, -600., short=False, rank=1),
                              target=lane(2., -600.)))["short_offsets"] == {}
    assert infer_offsets(dict(first, anchor=lane(1.5, -600., short=False),
                              target=lane(2., 1_000.), later=lane(4., -200.)))["short_offsets"] == {}


def test_scoring_never_turns_alias_or_arrival_mismatch_into_a_strict_match():
    stock = {"strict": lane(0., 100.), "alias": lane(1., 100.), "wrong_epoch": lane(2., 100.),
             "missing": lane(3., None)}
    mixed = dict(stock, strict=lane(0., 150.), alias=lane(1., 100.+ALIAS),
                 wrong_epoch=lane(2., 100., epoch=300), missing=lane(3., 200.))
    pairs, gaps = paired_measurements(stock, mixed, {k: [15., "anchor"] for k in mixed})
    assert pairs["strict"] == [(50., 65., True)]
    assert pairs["foldable_aliases"] == [(ALIAS, ALIAS+15., True)]
    assert gaps["corrected_without_strict_pair"] == 3 and gaps["corrected_without_installed"] == 1


def test_p95_is_interpolated_on_absolute_hz_and_tails_are_counted():
    measured = compare_errors([0., -100., 400.])
    assert measured["p95_absolute_hz"] == pytest.approx(370.)
    assert measured["over_150_hz"] == measured["over_250_hz"] == 1
