import pytest

from reports.ALGO08.v3.cyclic_presence import budget, classify, joined, roc, shape, summarize


def test_cyclic_shape_is_invariant_to_positive_gain_and_zero_safe():
    assert shape([8, 6, 4, 2]) == shape([80, 60, 40, 20]) == .75
    assert shape([0, 0, 0, 0]) == shape([2, 2, 2, 2]) == 0
    with pytest.raises(ValueError, match="ordered native comb peaks"):
        shape([0., 1., 3., 4.])


def test_full_observed_recall_keeps_ties_and_never_uses_negatives_to_set_threshold():
    rows = [dict(key=str(i), lane=i % 2, factor=positive, score=value)
            for i, (value, positive) in enumerate(((.1, ()), (.2, (0,)), (.2, ()), (.7, (0,))))]
    result = summarize(rows, .3)
    assert result["hindsight_threshold"] == .2
    assert result["hindsight"]["missed"] == []
    assert result["hindsight"]["skipped"] == [["0", 0]]
    assert result["calibrated"]["missed"] == [["1", 1]]
    assert [n for _, missed, n in roc(rows) if missed == 0] == [0, 0, 1]
    assert classify(rows, .2)["empty_kept"] == 1


def test_weak_budget_charges_all_short_opportunities():
    receipt = dict(weak_target_reduction_s=.6918179096654056, weak_short_cpu_s_per_call=.0010335453362903225,
                   cases={"DS30-0016": dict(short_lanes=1240, all_empty_short_lanes=839)})
    assert budget(0, receipt)["required_empty_skips"] == 670
    assert budget(66, receipt)["required_empty_skips"] == 749


def test_archive_join_requires_native_iq_identity_and_omits_full_anchors():
    scan = dict(measures={"16384": dict(scores=[9., 6., 2., 1.], cpu_ns=66)})
    original = dict(key="v0", lane=0, input_sha256="a", edge="upper", scans=[scan])
    observed = {"raw": {"dense": [original]}}
    label = dict(key="v0", lane=0, iq_sha256="a", metadata=dict(edge="upper"), mode="full", prefix=[1])
    assert joined(observed, {"dense": {"details": [label]}}, "dense") == []
    rows = joined(observed, {"dense": {"details": [dict(label, mode="short_primary")]}}, "dense")
    assert rows[0]["factor"] == [1]
    with pytest.raises(KeyError):
        joined(observed, {"dense": {"details": [dict(label, iq_sha256="b")]}}, "dense")
