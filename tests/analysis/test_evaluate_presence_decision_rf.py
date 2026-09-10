import copy
import json

import pytest

from tools.evaluate_presence_decision_rf import (
    diagnose,
    load_references,
    summarize,
    summarize_diagnostics,
    validate_reference,
    visits,
)
from tools.presence_decision_challenge import PROTOCOL


def test_rf_selection_is_bounded_and_all_edges_included():
    protocol = json.loads(PROTOCOL.read_text())
    assert visits(protocol) == list(range(240, 248)) + list(range(1440, 1448))
    for change in (
        {"rf_sweeps": [30, 30]},
        {"rf_sweeps": [30, 300]},
        {"rf_sessions": protocol["rf_sessions"][:2]},
        {"rf_sessions": [protocol["rf_sessions"][0]] * 4},
    ):
        with pytest.raises(ValueError):
            visits(protocol | change)


def test_unmatched_rf_is_never_counted_as_a_false_alarm():
    protocol = json.loads(PROTOCOL.read_text())
    record = {
        "rate_hz": 2500000,
        "reference_positive": [False] * 6,
        "decisions": {p: {"flagged": True, "associated": False} for p in protocol["policies"]},
    }
    positive = copy.deepcopy(record)
    positive["reference_positive"][3] = True
    result = summarize([record, positive], protocol)
    for policy in result.values():
        assert policy["2500000"] == {
            "dwells": 2,
            "reference_positive_dwells": 1,
            "flags_in_reference_positive": 1,
            "associated_reference_positive": 0,
            "unresolved_rf_dwells": 1,
            "flags_in_unresolved_rf": 1,
        }


def test_reused_reference_requires_exact_manifest_and_distinct_inventory(tmp_path):
    manifests = {"session-a": "sha256:a", "session-b": "sha256:b"}
    indices = [240, 241]
    rows = [{"session": s, "visit": i} for s in manifests for i in indices]
    freeze = tmp_path / "source-freeze.json"
    results = tmp_path / "results.jsonl"
    freeze.write_text(json.dumps({"sessions": manifests}))
    results.write_text("\n".join(map(json.dumps, rows)))
    assert len(load_references(tmp_path, manifests, indices)) == 4
    with pytest.raises(ValueError, match="manifests"):
        load_references(tmp_path, manifests | {"session-a": "changed"}, indices)
    for invalid in (rows[:-1], rows + rows[:1], rows[:3] + rows[:1]):
        results.write_text("\n".join(map(json.dumps, invalid)))
        with pytest.raises(ValueError, match="inventory"):
            load_references(tmp_path, manifests, indices)


def test_reused_reference_validates_iq_geometry_and_exact_large_counter():
    counter = 2**53 + 19
    row = {
        "iq_sha256": "a",
        "rate_hz": 2500000,
        "edge": "lower",
        "rx": 1,
        "source_counter": str(counter),
    }
    expected = dict(input_sha="a", rate=2500000, edge="lower", counter=counter)
    validate_reference(row, **expected)
    for field, value in (
        ("iq_sha256", "b"),
        ("rate_hz", 5000000),
        ("edge", "upper"),
        ("rx", 0),
        ("source_counter", str(counter + 1)),
        ("source_counter", float(counter)),
    ):
        with pytest.raises(ValueError, match="IQ identity"):
            validate_reference(row | {field: value}, **expected)


def diagnostic_case():
    protocol = json.loads(PROTOCOL.read_text())
    # Epochs straddle the fractional frame seam; never convert device counters.
    candidate = {
        "epoch": 3333,
        "fractional_offset_samples": 0.4,
        "tracking_cfo_hz": 70000,
        "exact_score": 0.3,
        "margin": 0.2,
        "fractional_complete": 1,
    }
    reference = {
        "epoch_sample": 0,
        "fractional_offset_samples": 0.1,
        "tracking_cfo_hz": 70001,
        "exact_score": 0.3,
        "margin": 0.2,
    }
    row = {
        "rate_hz": 2500000,
        "selected_window": 0,
        "candidates": [candidate],
        "reference_candidates": [[], [reference], [], [], [], []],
        "reference_positive": [False, True, False, False, False, False],
    }
    result = {
        "confirmation_count": 6,
        "confirmation_window_mask": 63,
        "rank": {"order": list(range(6))},
        "confirmations": [
            {"candidates": [copy.deepcopy(candidate)], "candidate_count": 1} for _ in range(6)
        ],
    }
    return protocol, row, result


def test_cross_window_comparison_is_separate_and_does_not_replace_original_decision():
    protocol, row, result = diagnostic_case()
    untouched = copy.deepcopy(row)
    diagnostic = diagnose(row, result, protocol)
    assert row == untouched
    for windows in diagnostic["comparisons"].values():
        assert windows[0]["within_dwell_associated"]
        assert not windows[0]["same_window_associated"]
        assert windows[1]["same_window_associated"]
    row["diagnostics"] = diagnostic
    unresolved = copy.deepcopy(row)
    unresolved["reference_candidates"] = [[] for _ in range(6)]
    unresolved["reference_positive"] = [False] * 6
    unresolved["diagnostics"] = diagnose(unresolved, result, protocol)
    summary = summarize_diagnostics([row, unresolved], protocol)
    for policy in summary.values():
        rate = policy["2500000"]
        assert rate["1"]["same_window_associated"] == 0
        assert rate["1"]["within_dwell_associated"] == 1
        assert rate["2"]["same_window_associated"] == 1
        assert rate["1"]["unresolved_rf_dwells"] == rate["1"]["flags_in_unresolved_rf"] == 1
        assert "false_flags" not in rate["1"]


def test_diagnostic_requires_complete_inventory_and_reproduced_single_confirmation():
    protocol, row, result = diagnostic_case()
    for change in (
        {"confirmation_count": 1},
        {"confirmation_window_mask": 62},
        {"rank": {"order": [1, 0, 2, 3, 4, 5]}},
        {"rank": {"order": [0] * 6}},
    ):
        with pytest.raises(ValueError):
            diagnose(row, result | change, protocol)
    changed = copy.deepcopy(result)
    changed["confirmations"][0]["candidates"][0]["exact_score"] += 0.01
    with pytest.raises(ValueError, match="first confirmation changed"):
        diagnose(row, changed, protocol)
