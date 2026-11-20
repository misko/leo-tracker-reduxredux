import json

import pytest

from tools.pipeline_eval.qualification import frontier_whole_replay as study
from tools.pipeline_eval.qualification import frontier_whole_replay_candidate as admission
from tools.pipeline_eval.qualification import frontier_whole_replay_results as result


def test_blind_hash_selection_excludes_old_cases_and_keeps_rejected_rank(monkeypatch):
    def inputs(digest):
        return {"recording": {"segments": [{"sha256": digest}]}}

    rows = {
        "DS26-0001": inputs("0"),
        "DS26-0002": inputs("2"),
        "DS26-0003": inputs("1"),
        "DS29-0001": inputs("0"),
        "DS29-0002": inputs("4"),
        "DS29-0003": inputs("3"),
    }
    sources = {"earlier": {"cases": ["DS26-0001", "DS29-0001"]}}
    called = []

    def require(ident):
        called.append(ident)
        if ident == "DS26-0003":
            raise ValueError("archive release unavailable")
        return ident, {}

    monkeypatch.setattr(study.whole_iq, "binding", require)
    monkeypatch.setattr(
        study.capture_release,
        "read_capture",
        lambda ident: dict(input_manifest_sha256=ident, edge="lower"),
    )
    cases, ledger = study.selected(rows, sources)
    assert called == ["DS26-0003", "DS26-0002", "DS29-0003"]
    assert [row["id"] for row in cases] == ["DS26-0002", "DS29-0003"]
    assert ledger["ranking"]["DS26"]["ineligible"][0]["id"] == "DS26-0003"


def test_gate_rejects_confirmation_that_reports_only_one_dataset():
    primary, matched, confirm = (
        dict(n=count, causal_physical_passes=passed) for count, passed in [(16, 5), (8, 8), (8, 2)]
    )
    stats = dict(primary_miss=primary, primary_matched=matched, confirmation=confirm)
    admission.check_gate(stats, [{"case": "DS26-0001"}, {"case": "DS29-0001"}])
    with pytest.raises(ValueError, match="activation gate"):
        admission.check_gate(stats, [{"case": "DS26-0001"}, {"case": "DS26-0002"}])


def candidate(rank, value, *, passed):
    return dict(candidate_rank=rank, fractional_margin=value, passed_fractional_margin_gate=passed)


def visit(probes, *, sample_end=100):
    return dict(visit=0, segment=0, status="processed", sample_end=sample_end, probes=probes)


def test_changes_to_native_arrays_do_not_substitute_changed_sample_support():
    best = candidate(1, 4.0, passed=True)
    runner_up = candidate(2, 4.0, passed=True)
    failed = candidate(0, 90.0, passed=False)
    old = [dict(receiver_id=1, candidates=[failed])]
    new = [dict(receiver_id=1, candidates=[runner_up, failed, best])]
    timing = [dict(visit=0, lane=0, wall_s=0.020, cpu_s=0.018)]
    control = list(result.trace_rows("DS26-1", "control", ([visit(old)], timing, "")))
    intervention = list(result.trace_rows("DS26-1", "candidate", ([visit(new)], timing, "")))
    assert intervention[0]["probes"][0]["winner"] == best
    assert result.compare_probes(control, intervention)["new_positive_probes"] == 1
    mutated = list(
        result.trace_rows("DS26-1", "candidate", ([visit(new, sample_end=101)], timing, ""))
    )
    with pytest.raises(ValueError, match="clock drift"):
        result.compare_probes(control, mutated)


def test_candidate_lane_trace_authenticates_call_order_and_timings(tmp_path):
    replay = tmp_path / "recording"
    replay.mkdir()
    for lane in range(2):
        event = dict(
            visit=0,
            hints=[3000, None],
            changed=[True, False],
            scout_wall_ns=1_000_000,
            scout_cpu_ns=999_000,
            native_wall_ns=2_000_000,
            native_cpu_ns=1_999_000,
        )
        footer = dict(visits=1, lanes_with_hint=[1, 0], changed_lanes=[1, 0])
        (replay / f"replayed-{lane}.log").write_text(
            f"differential-visit: {json.dumps(event)}\n"
            f"differential-runtime-result: {json.dumps(footer)}\n"
        )
    rows = [
        dict(visit=10, lane=0, wall_s=0.004, status="processed"),
        dict(visit=11, lane=1, wall_s=0.005, status="processed"),
    ]
    assert result.scout_trace(tmp_path, rows)[0]["changed_lanes"] == [1, 0]
    assert rows[0]["differential"]["hints"] == [3000, None]
    rows[0]["wall_s"] = 0.002
    with pytest.raises(ValueError, match="clocks"):
        result.scout_trace(tmp_path, rows)
