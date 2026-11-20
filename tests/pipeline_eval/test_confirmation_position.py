import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import confirmation_position as trial
from tools.pipeline_eval.qualification import confirmation_position_full as full
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.variants import pilot_confirmation


def proposal(rank, passed=True):
    return dict(
        candidate_rank=rank,
        integer_epoch_sample=2301,
        fractional_epoch_offset_samples=-0.4,
        fractional_tracking_cfo_hz=64_125.0,
        fractional_exact_score=0.55,
        fractional_control_score=0.2,
        fractional_margin=0.35 if passed else 0.01,
        passed_fractional_margin_gate=passed,
    )


def capture_visit(visit, probes):
    return dict(
        segment=0,
        sequence=visit,
        visit=visit,
        iq_sha256=f"test-iq-{visit}",
        status="processed" if probes else "invalid_capture",
        reason=None if probes else "invalid sample support",
        sample_start=visit * 200_000,
        sample_end=(visit + 1) * 200_000,
        probes=[
            dict(visit_index=visit, receiver_id=rx, probe_start_ms=0, candidates=peaks)
            for rx, peaks in enumerate(probes)
        ],
    )


def measurement(ordinary, decisions):
    return dict(
        {key: ordinary[key] for key in trial.SUPPORT},
        candidates=[
            dict(candidate, receiver=probe["receiver_id"], confirmation={"passed": passed})
            for (probe, candidate), passed in zip(
                ((p, c) for p in ordinary["probes"] for c in p["candidates"]),
                decisions,
                strict=True,
            )
        ],
    )


def test_partial_gate_only_removes_rejected_complete_positives():
    selected = capture_visit(0, ([proposal(0), proposal(2, passed=False)], [proposal(1)]))
    outside = capture_visit(1, ([proposal(0)], []))
    invalid = capture_visit(2, [])
    candidate_lists = selected["probes"] + outside["probes"]
    ordinary = dict(
        source=dict(probes=candidate_lists, analysis_manifest_sha256="original"),
        provenance=dict(excluded_windows=[2]),
        clock_anchor={"counter": 0},
    )
    visits = {row["visit"]: row for row in (selected, outside, invalid)}
    before = deepcopy(ordinary)

    gate = trial.decisions(
        visits, [measurement(selected, [False, True, True]), measurement(invalid, [])]
    )
    derived, metrics = trial.apply_gate(ordinary, visits, gate, "test", "test")

    assert gate == {0: {(0, 0): False, (1, 1): True}, 2: {}}
    assert ordinary == before
    assert derived["source"]["probes"][0]["candidates"] == [proposal(2, False)]
    assert derived["source"]["probes"][1:] == before["source"]["probes"][1:]
    assert derived["clock_anchor"] == before["clock_anchor"]
    assert derived["provenance"]["excluded_windows"] == [2]
    assert metrics["scheduled_gate_visits"] == 2
    assert metrics["valid_gate_visits"] == 1
    assert metrics["removed_original_positive_candidates"] == 1
    assert derived["source"]["analysis_manifest_sha256"] != "original"


@pytest.mark.parametrize("change", ("iq_sha256", "fractional_margin", "candidate_rank"))
def test_rejects_approximate_candidate_or_window_binding(change):
    original = capture_visit(0, ([proposal(0)], []))
    selected = measurement(original, [True])
    if change == "iq_sha256":
        selected[change] = "different"
    else:
        selected["candidates"][0][change] += 0.000001
    with pytest.raises(ValueError, match="late-pilot measurement"):
        trial.decisions({0: original}, [selected])


def test_whole_gate_reconstructs_native_rank_holes_without_new_hypotheses():
    visited = capture_visit(0, ([proposal(0, passed=False), proposal(2)], []))
    rx0, rx1 = full.native_rows(visited["probes"])
    assert rx1["candidates"] == []
    assert [p["fractional_epoch"]["status"] for p in rx0["candidates"]] == [
        "not_evaluated",
        "not_evaluated",
        "complete",
    ]
    assert rx0["candidates"][2]["fractional_epoch"]["tracking_cfo_hz"] == 64_125.0


def test_whole_gate_checks_terminal_coverage_and_selected_overlap(tmp_path):
    original = capture_visit(0, ([proposal(0)], []))
    visits = {0: original}
    overlap = {0: {(0, 0): True}}
    path = tmp_path / "gate.jsonl"
    row = dict(
        {k: v for k, v in original.items() if k != "probes"},
        confirmation_cpu_s=0.01,
        decisions=[[0, 0, True]],
    )
    method = _sha(Path(pilot_confirmation.__file__))
    terminal = dict(terminal=True, method_sha256=method)
    path.write_text(json.dumps(row) + "\n" + json.dumps(terminal) + "\n")
    gate, cpu_s = full.read_gate(path, visits, overlap)
    assert gate == overlap and cpu_s == 0.01

    row["decisions"][0][2] = False
    path.write_text(json.dumps(row) + "\n" + json.dumps(terminal) + "\n")
    with pytest.raises(ValueError, match="changed a frozen sample decision"):
        full.read_gate(path, visits, overlap)
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="lacks terminal authority"):
        full.read_gate(path, visits, overlap)
