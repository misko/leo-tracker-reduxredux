"""Check blind bracket geometry, abstention and signed native scoring semantics."""

import pytest

from reports.ALGO08.v3.empty_graph_rescue import ALIAS, HERTZ, SAMPLE_RATE, SINGLE, bracket, factor_readout, proposals


def row(i, sec, hz=None, *, short=True, lift=0, channel=3):
    factor = None if hz is None else {HERTZ: hz, "integer_epoch_sample": 8, "fractional_epoch_offset_samples": -.25}
    return dict(id=i, counter=int(SAMPLE_RATE*sec), radio=0, short=short, lift=lift, factor=factor,
                row=dict(visit_index=int(sec*20), edge="upper", channel=channel, actual_rf_hz=11_100_000_000,
                         receiver_id=0))


def test_observable_interpolation_exports_donor_epochs_and_unequal_weight():
    a, b, t = row("a",0,900.), row("b",2,1_700.), row("t",.5)
    result = proposals({x["id"]:x for x in (a,b,t)}, {("arc",0):[a,b]})
    target = result["opportunities"]["t"]
    used, = target["brackets"]
    assert target["status"] == SINGLE and target["counter"] == SAMPLE_RATE//2
    assert used["right_weight"] == .25 and used["signed_centers_hz"] == [1_100.]
    assert used["half_width_hz"] == 775. and used["left"]["observation_id"] == "a"
    assert used["right"]["fractional_epoch_offset_samples"] == -.25


def test_alias_change_and_overlapping_pieces_abstain_even_if_a_branch_looks_close():
    a, b, t = row("a",0,100_000.), row("b",2,100_500.-ALIAS,lift=1), row("t",1)
    case = {x["id"]:x for x in (a,b,t)}
    one = proposals(case,{("arc",0):[a,b]})["opportunities"]["t"]
    assert one["status"] == "different_neighbor_alias_lifts"
    assert one["brackets"][0]["signed_centers_hz"] == pytest.approx([100_250.,100_250.-ALIAS])
    c, d = row("c",.5,200.), row("d",1.5,1_100.)
    both = proposals(case,{("arc",0):[a,b],("another",0):[c,d]})["opportunities"]["t"]
    assert both["status"] == "multiple_graph_pieces"


def test_enrollment_and_out_of_range_rejections_keep_empty_slots_in_denominator():
    a, b = row("a",0,900.), row("b",4,1_000.)
    far, wrong_rf, anchor = row("t",1), row("w",2,channel=1), row("z",2,short=False)
    total = proposals({x["id"]:x for x in (far,wrong_rf,anchor)}, {("arc",0):[a,b]})
    assert total["empty_short_count"] == 2 and total["no_piece_bracket"] == 1
    assert total["rejected_bracket_counts"] == {"bracket_spacing":1}
    assert bracket(("arc",0),row("a",0,0.),SAMPLE_RATE,row("b",2,20_000.)) == (None,"lifted_secant_out_of_range")
    assert bracket(("arc",0),row("a",0,5_000_100.),SAMPLE_RATE,row("b",2,5_000_200.)) == (None,"outside_adc_range")


def test_score_counts_reference_empty_and_alias_only_separately():
    reference = {"a":row("a",1,1_010.),"b":row("b",2,1_010.+ALIAS),"e":row("e",3),"m":row("m",4,3_000.)}
    entry = dict(status=SINGLE,brackets=[dict(signed_centers_hz=[1_000.],half_width_hz=400.)])
    result = factor_readout(reference.keys(),reference,dict(a=entry,b=entry,e=entry))
    assert result["counts"]["installed_positives"] == 3 and result["counts"]["all_empty_opportunities"] == 4
    assert result["counts"]["interval_hits"] == 1 and result["counts"]["alias_roll_only_hits"] == 1
    assert result["counts"]["installed_empty_selected"] == 1 and result["interval_recall"] == pytest.approx(1/3)
