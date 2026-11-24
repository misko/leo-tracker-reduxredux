"""Unit tests for the fixed observed-track CFO interpolation study."""

import pytest

from reports.ALGO08.v3.track_cfo_denoise import ALIAS, HERTZ, SAMPLE_RATE, bracket, describe, paired_rows, proposed_offsets


def lane(i, t, hz, *, lift=0, short=True, radio=0, epoch=0.):
    return dict(id=i, counter=int(SAMPLE_RATE*t), short=short, lift=lift,
                factor={HERTZ: hz, "integer_epoch_sample": 50, "fractional_epoch_offset_samples": epoch},
                row=dict(receiver_id=radio, actual_rf_hz=11_100_000_000, channel=3, edge="upper"))


def test_interpolation_preserves_the_signed_lift_and_uses_actual_unequal_spacing():
    a = lane("a", 0., -110_500., lift=1)
    b = lane("b", .25, 117_000.)
    c = lane("c", 1.0, 118_000., short=False)
    delta, reason = bracket(a,b,c)
    assert reason == "eligible"
    assert delta == pytest.approx(.75*(-227_500.+ALIAS)+.25*1_000.)
    support, changes, counts = proposed_offsets({"piece": [a,b,c]})
    assert support == ["a","b"] and counts == {"eligible":1}
    assert changes["b"]["neighbors"] == ["a","c"] and changes["b"]["graph_alias_changes"]
    assert changes["b"]["donor_aperture"] == "1_full_neighbors"
    assert b["factor"][HERTZ] == 117_000.


def test_gates_reject_wide_gap_wrong_receiver_wrong_slope_and_large_innovation():
    a = lane("a", 0., 0.)
    b = lane("b", .25, 50.)
    assert bracket(a,b,lane("c",1.5,100.)) == (None,"spacing")
    assert bracket(a,b,lane("c",.5,100.,radio=1)) == (None,"rf_lane")
    assert bracket(a,b,lane("c",.5,5_001.)) == (None,"slope")
    assert bracket(a,b,lane("c",.5,701.)) == (None,"innovation")
    assert bracket(a, lane("b",.25,50.,short=False), lane("c",.5,100.)) == (None,"full_center")


def test_no_new_support_is_created_when_offsets_cross_pair_threshold():
    ids = list("abcd")
    stock = {x: lane(x,k,0.) for k,x in enumerate(ids)}
    candidate = {"a": lane("a",0.,249.), "b": lane("b",1.,251.), "c": lane("c",2.,100.,epoch=3.),
                 "d": lane("d",3.,ALIAS)}
    plan = {"all_unambiguous_graph_shorts": ids, "proposals": {
        "a": {"interpolation_minus_center_hz": 4., "donor_aperture": "0_full_neighbors"},
        "b": {"interpolation_minus_center_hz": -4., "donor_aperture": "0_full_neighbors"}}}
    rows, coverage = paired_rows(stock,candidate,plan)
    assert rows["strict"] == [(249.,4.,True)]
    assert coverage == {"outside_epoch_window": 1, "foldable_alias_epoch_close": 1, "proposed_without_strict_pair": 1}
    result = describe(rows)["strict"]["proposed_only"]
    assert result["half_blend"]["mae_hz"] == 251.
    assert result["interpolation_only"]["mae_hz"] == 253.


def test_adjacent_blends_share_original_measurements_in_their_covariance():
    # At equal spacing rows 1 and 2 are [1/4,1/2,1/4,0] and [0,1/4,1/2,1/4].
    # Applying these to independent unit-noise observations would create covariance 1/4.
    a, b, c, d = [lane(i,k/2,200. if k in (1,2) else 0.) for k,i in enumerate("abcd")]
    _, plan, _ = proposed_offsets({"piece": [a,b,c,d]})
    assert [plan[i]["interpolation_minus_center_hz"] for i in ("b","c")] == [-100.,-100.]
    A_mid = [(1/4,1/2,1/4,0.), (0.,1/4,1/2,1/4)]
    assert sum(x*y for x,y in zip(*A_mid, strict=True)) == .25
