"""Portable quality-accounting tests; no hardware, store or fabricated RF truth."""

import copy
import json

import pytest

from tools.evaluate_presence_dwell_holdout import PROTOCOL, compare, summarize, validate


@pytest.fixture
def protocol():
    return json.loads(PROTOCOL.read_text())


def candidate(**changes):
    return dict(
        epoch=123,
        fractional_offset_samples=0.25,
        tracking_cfo_hz=50000.0,
        fractional_complete=True,
        exact_score=0.3,
        margin=0.08,
        **changes,
    )


def evidence(candidates, selected=2):
    return dict(
        rank=dict(order=[selected]),
        confirmation_count=1,
        confirmation_window_mask=1 << selected,
        confirmations=[dict(candidate_count=len(candidates), candidates=candidates)],
    )


def reference(native, window=2):
    expected = dict(native)
    expected["epoch_sample"] = expected.pop("epoch")
    groups = [[] for _ in range(6)]
    groups[window] = [expected]
    return groups


def test_frozen_selection_is_rate_balanced_and_includes_contiguous_targets(protocol):
    indices = validate(protocol)
    assert len(indices) == 48
    assert indices[:32] == list(range(160, 192))
    assert indices[-1] == 2087


@pytest.mark.parametrize(
    "key,value",
    [
        ("receiver", 0),
        ("receiver", True),
        ("maximum_confirmations", 2),
        ("dwell_ms", 100),
        ("reference_candidates", 2),
        ("seeded", True),
        ("live_rf", True),
        ("screen_bins", 1024),
        ("sweeps", [20, 21, 22]),
        ("policy", {"minimum_exact_score": 0.15, "minimum_margin": 0.025}),
    ],
)
def test_unreviewed_geometry_or_thresholds_rejected(protocol, key, value):
    protocol[key] = value
    with pytest.raises(ValueError):
        validate(protocol)


def test_duplicate_sessions_rejected(protocol):
    protocol["sessions"][1] = protocol["sessions"][0]
    with pytest.raises(ValueError):
        validate(protocol)


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_fractional_association_and_same_window_support(protocol, rate):
    c = candidate()
    checked = compare(evidence([c]), reference(c), rate, protocol)
    assert checked["detected"] and checked["matched_selected"]
    assert checked["reference_any"] and checked["reference_selected"]
    assert checked["outcome"] == 1


def test_any_window_is_not_same_window_association(protocol):
    c = candidate()
    checked = compare(evidence([c]), reference(c, window=5), 2500000, protocol)
    assert checked["reference_any"] and checked["detected"]
    assert not checked["reference_selected"] and not checked["matched_selected"]
    assert checked["unassociated_flag"]  # Not labeled a false positive.


def test_incomplete_fractional_candidate_is_unknown_not_miss(protocol):
    c = candidate()
    incomplete = dict(c, fractional_complete=False)
    checked = compare(evidence([incomplete]), reference(c), 5000000, protocol)
    assert checked["outcome"] == 0 and checked["unknown_on_reference"]
    assert not checked["evaluated_miss_on_reference"]


def test_complete_subthreshold_is_evaluated_miss_on_reference(protocol):
    c = candidate()
    low = dict(c, exact_score=0.174)
    checked = compare(evidence([low]), reference(c), 5000000, protocol)
    assert checked["evaluated_miss_on_reference"] and checked["outcome"] == 2
    assert not checked["detected"]


def test_no_reference_is_not_proven_absence(protocol):
    c = candidate()
    checked = compare(evidence([c]), [[] for _ in range(6)], 2500000, protocol)
    assert checked["unassociated_flag"] and checked["detected"]
    assert not checked["reference_any"]
    assert "false_positive" not in checked and "absent" not in checked


def test_absolute_and_margin_boundaries_inclusive(protocol):
    c = dict(candidate(), exact_score=0.175, margin=0.025)
    assert compare(evidence([c]), reference(c), 2500000, protocol)["detected"]


def test_miss_bursts_do_not_cross_unread_sweeps_or_unknowns(protocol):
    c = dict(candidate(), exact_score=0.1)
    checked = compare(evidence([c]), reference(candidate()), 2500000, protocol)
    row = dict(
        session_id="s",
        channel=1,
        edge="lower",
        rate_hz=2500000,
        native={"total_wall_ms": 2.0},
        comparison=checked,
    )
    contiguous = [dict(row, visit=v) for v in (160, 168, 176, 184)]
    result = summarize(contiguous)
    assert len(result["consecutive_three_miss_bursts"]) == 2
    assert result["consecutive_three_miss_bursts"][0]["reference_supported_visits"] == 3
    assert result["groups"]["2500000"]["flag_recall_any_reference"] == 0
    assert result["groups"]["5000000"]["flag_recall_any_reference"] is None
    gap = [dict(row, visit=v) for v in (160, 168, 1120)]
    assert not summarize(gap)["consecutive_three_miss_bursts"]
    unknown = copy.deepcopy(contiguous)
    unknown[1]["comparison"]["outcome"] = 0
    assert not summarize(unknown)["consecutive_three_miss_bursts"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("confirmation_count", 2),
        ("confirmation_window_mask", 1),
    ],
)
def test_confirmation_coverage_not_silently_changed(protocol, field, value):
    c = candidate()
    result = evidence([c])
    result[field] = value
    with pytest.raises(ValueError):
        compare(result, reference(c), 5000000, protocol)
