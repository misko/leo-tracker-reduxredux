"""Test alias-free owner joins and time exposure on small signed-row examples."""

import pytest

from reports.ALGO08.v3.missed_owner_support import HERTZ, SAMPLE_RATE, candidate_neighbors, classes, context_counts, owner_times
from signed_cfo_time import ALIAS


def lane(t, hz, *, radio=0, short=True, epoch=0):
    factor = None if hz is None else {HERTZ: hz, "integer_epoch_sample": epoch, "fractional_epoch_offset_samples": 0.}
    return dict(radio=radio, counter=int(t*SAMPLE_RATE), short=short, factor=factor,
                row=dict(edge="lower", channel=2, receiver_id=radio, actual_rf_hz=11_000_000_000,
                         candidates=[] if factor is None else [factor]))


def test_installed_detection_classes_are_disjoint_and_do_not_fold_aliases():
    a = {"A": lane(0., 100.), "B": lane(1., 100.), "C": lane(2., 100.), "D": lane(3., 100., short=False),
         "E": lane(4., None), "F": lane(5., None)}
    b = dict(a, A=lane(0., None), B=lane(1., 101.), C=lane(2., 100.+ALIAS), E=lane(4., 100.))
    groups, unmatched = classes(a, b)
    assert groups == dict(missing={"A"}, common={"B"}, disagreeing={"C"}, full_anchor={"D"})
    assert unmatched == {"short_candidate_only":1, "short_both_empty":1}


def test_candidate_neighbor_context_ignores_the_scored_row_and_other_radio():
    data = {"a":lane(0.,120.), "b":lane(1.,200.), "c":lane(2.9,215.), "other_radio":lane(4.0,44.,radio=1),
            "solo":lane(30.,75.)}
    indexed = candidate_neighbors(data)
    assert context_counts({"b","c","solo"}, data, indexed) == dict(before=1, after=0, both=1, neither=1)


def test_frozen_owner_stream_detects_new_bridge_gap_and_boundary_loss():
    installed = {name: lane(t, 100.) for name,t in (("A",0.),("B",4.),("C",8.),("D",12.),("E",14.),("F",30.))}
    owners = {name:(10,"conditional") for name in installed}
    groups = {"missing":{"B","C","E","F"}, "common":{"A","D"}, "disagreeing":set(),"full_anchor":set()}
    current = owner_times(owners, installed, groups)
    metrics = current["metrics"]
    assert metrics["original"]["span_s"] == pytest.approx(14.)
    assert metrics["without_missing_shorts"]["span_s"] == pytest.approx(12.)
    assert metrics["without_missing_shorts"]["gaps_over_8_s"] == 1
    assert metrics["without_missing_shorts"]["wholly_erased_groups"] == 1
    assert metrics["without_missing_shorts"]["quadratic_design_s4"] == 0.
    assert current["missing_owner_placement_vs_common"] == dict(between_common=2, after_common=1, no_common_owned_short=1)
