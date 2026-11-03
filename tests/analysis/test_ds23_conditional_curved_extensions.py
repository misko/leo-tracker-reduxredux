"""Whole-fragment canonical-ID exclusivity for position-only additions."""

from probe_ds23_conditional_curved_extensions import disjoint_additions


def test_curved_additions_cannot_duplicate_calibration_or_linear_evidence():
    tracks = [dict(key=str(i), observation_ids=[str(i)+":"+str(j) for j in range(6)]) for i in range(4)]
    rows = [dict(component=str(i), association_source="frozen_calibration_extension") for i in range(4)]
    occupied = set(tracks[0]["observation_ids"]+tracks[1]["observation_ids"])
    selected = disjoint_additions(rows, tracks, {0,1,2}, occupied)
    assert [i for _, i in selected] == [2]
    assert len(occupied) == 12


def test_duplicate_or_overlapping_new_fragments_never_count_a_probe_twice():
    tracks = [dict(key="a", observation_ids=list("abcdef")),
              dict(key="b", observation_ids=list("fghijk")),
              dict(key="c", observation_ids=list("llllll"))]
    rows = [dict(component=t["key"], association_source="frozen_calibration_extension") for t in tracks]
    selected = disjoint_additions(rows, tracks, {0,1,2}, set())
    assert [i for _, i in selected] == [0]
