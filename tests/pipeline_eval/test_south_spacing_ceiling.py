import pytest

from reports.ALGO08.v3 import south_spacing_ceiling as check


def row(name, counter, *, hz=0., radio=0, phase=0., lift=0, piece="p", ordinal=0):
    offset = (phase-(3*counter % 40_000)/3) % check.odd.PERIOD
    return dict(id=name,counter=counter,short=True,ordinal=ordinal,lift=lift,piece=(piece,0),
                row=dict(edge="falling",channel=4,actual_rf_hz=41,receiver_id=radio),
                factor={check.odd.HERTZ:hz,"integer_epoch_sample":int(offset),
                        "fractional_epoch_offset_samples":offset-int(offset)})


def test_spacing_only_preserves_identical_operands_and_ordinary_in_range_prediction():
    second = check.odd.ADC
    l, r = row("l",0,hz=-470.),row("r",2*second,hz=-70.)
    assert check.ORIGINAL_INTERPOLATE(l,second,r) == (None,"spacing")
    p, reason = check.spacing_only(l,second,r)
    assert reason == "proposed"
    assert p["cfo_hz"] == -270.
    assert p["donor_counters"] == [0,2*second]
    assert p["left_wait_samples"] == p["right_wait_samples"] == second
    assert p["arrival"] == 0.
    r = row("r",second,hz=-70.)
    assert check.spacing_pass(l,second//2,r) == check.ORIGINAL_INTERPOLATE(l,second//2,r)
    assert check.spacing_only(l,second//2,r) == check.ORIGINAL_INTERPOLATE(l,second//2,r)
    with pytest.raises(ValueError,match="chronological straddle"):
        check.spacing_only(l,2*second,r)


def test_later_alias_slope_and_antipodal_phase_guards_still_apply():
    second = check.odd.ADC
    l = row("l",0)
    assert check.spacing_only(l,second,row("r",2*second,lift=1)) == (None,"ambiguous_alias_branch")
    assert check.spacing_only(l,second,row("r",2*second,hz=16_001)) == (None,"slope")
    r = row("r",2*second,phase=check.odd.PERIOD/2)
    assert check.spacing_only(l,second,r) == (None,"ambiguous_arrival_arc")


def test_only_registered_spacing_failures_reach_same_winner_and_innovation():
    second = check.odd.ADC
    left, right = (row("left",0,hz=100.), row("right",2*second,hz=300.,ordinal=1))
    others = {
        "left_peer":row("left_peer",0,hz=100.,radio=1,piece="other"),
        "right_peer":row("right_peer",2*second,hz=300.,radio=1,piece="separate",ordinal=1),
    }
    retained = dict(left=left,right=right,**others)
    held = {"target":dict(lane=("falling",4,41,0),counter=second),
            "peer":dict(lane=("falling",4,41,1),counter=second)}
    old = dict(proposals={},release_forecast_eligibility=dict(spacing=1,different_or_nonadjacent_piece=1))
    spacing, proposals, flow = check.forecast(old,held,retained,retained)
    assert set(spacing) == set(proposals) == {"target"}
    assert flow == dict(proposed=1,different_or_nonadjacent_piece=1)
    original = retained | {"target":row("target",second,hz=300.,phase=12.)}
    edits, counts, evidence = check.edits(held,original,spacing,proposals)
    assert counts == {"eligible":1}
    assert edits["target"]["updated_hz"] == 250.
    assert edits["target"]["arrival"] == pytest.approx(12.)
    assert evidence["target"]["candidate_positive"]
    original["target"] = row("target",second,hz=900.)
    assert check.edits(held,original,spacing,proposals)[1] == {"more_than_one_bin":1}
    original["target"]["factor"] = None
    assert check.edits(held,original,spacing,proposals)[1] == {"target_empty":1}
