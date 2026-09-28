from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from score import score
import score as local_score


def _baseline(case="ds7-s-v0", margin=0.03, candidates=None, start=0):
    entries = candidates if candidates is not None else [{"epoch_sample": 100, "tracking_cfo_hz": 1000.0, "margin": margin}]
    for entry in entries:
        entry["passed_margin_gate"] = entry["margin"] >= 0.025
    return {"case_id": case, "status": "ok", "context": {"rate_hz": 2_500_000}, "result": {"probes": [{"receiver_id": 0, "probe_start_ms": start, "candidates": entries}]}}


def _arm(case="ds7-s-v0", mask=1, order=(0, 1, 2, 3, 4, 5), candidates=None):
    entries = candidates if candidates is not None else [{"epoch": 100, "fractional_offset_samples": 0.25, "tracking_cfo_hz": 1000.0, "margin": 0.03, "fractional_complete": 1}]
    confirmations = [{"candidate_count": len(entries), "candidates": entries} for bit in range(mask.bit_length()) if mask & (1 << bit)]
    receiver = {"receiver": 0, "result": {"rank": {"order": list(order)}, "confirmation_count": len(confirmations), "confirmation_window_mask": mask, "confirmations": confirmations}}
    receiver_one = {"receiver": 1, "result": {"rank": {"order": list(order)}, "confirmation_count": 0, "confirmation_window_mask": 0, "confirmations": []}}
    return {"type": "job", "case_id": case, "status": "processed", "receivers": [receiver, receiver_one]}


def _inputs(*cases): return {"case_ids": list(cases)}


def test_window_and_individual_candidate_identity_are_counted_separately():
    baseline = _baseline(candidates=[
        {"epoch_sample": 100, "tracking_cfo_hz": 1000.0, "margin": .03},
        {"epoch_sample": 101, "tracking_cfo_hz": 1000.0, "margin": .03},
    ])
    result = score([baseline], [_arm()], _inputs("ds7-s-v0"))
    assert result["windows"]["baseline_positive"] == 1
    assert result["windows"]["matched_baseline_positive_windows_identity"] == 1
    assert result["candidates"]["baseline_positive"] == 2
    assert result["candidates"]["positive_candidate_identity_recovered_one_to_one"] == 1


def test_executed_mask_maps_to_20ms_windows_and_dropped_window_is_not_evaluated():
    baseline0 = _baseline(case="ds7-s-v0", start=0)
    baseline20 = _baseline(case="ds7-s-v1", start=20)
    arm0 = _arm(case="ds7-s-v0", mask=1)
    arm1 = _arm(case="ds7-s-v1", mask=0)
    result = score([baseline0, baseline20], [arm0, arm1], _inputs("ds7-s-v0", "ds7-s-v1"))
    assert result["windows"]["arm_ranked"] == 24
    assert result["windows"]["arm_executed"] == 1
    assert result["windows"]["baseline_positive_evaluated"] == 1


def test_fractional_epoch_is_used_for_identity_gate():
    baseline = _baseline()
    # At 2.5 MHz, 5.1 samples is 2.04 us and must miss the exact 2 us gate.
    arm = _arm(candidates=[{"epoch": 105, "fractional_offset_samples": .1, "tracking_cfo_hz": 1000., "margin": .03, "fractional_complete": 1}])
    result = score([baseline], [arm], _inputs("ds7-s-v0"))
    assert result["windows"]["baseline_positive_positive_again_activity"] == 1
    assert result["candidates"]["positive_candidate_identity_recovered_one_to_one"] == 0


def test_boundary_difference_is_explicit_and_not_silently_equal():
    baseline = _baseline(margin=.025)
    arm = _arm(candidates=[{"epoch": 100, "fractional_offset_samples": 0., "tracking_cfo_hz": 1000., "margin": .025, "fractional_complete": 1}])
    result = score([baseline], [arm], _inputs("ds7-s-v0"))
    assert result["windows"]["baseline_positive"] == 1
    assert result["windows"]["baseline_positive_positive_again_activity"] == 0
    assert "strictly" in result["boundary_difference"]


def test_missing_or_duplicate_case_receipt_is_fatal():
    baseline = _baseline()
    try:
        score([baseline], [_arm()], _inputs("ds7-s-v0", "ds7-s-v1"))
    except ValueError as error:
        assert "cohort does not equal planned" in str(error)
    else: raise AssertionError("missing planned receipt must fail")
    try:
        score([baseline], [_arm(), _arm()], _inputs("ds7-s-v0"))
    except ValueError as error:
        assert "duplicate ARM case" in str(error)
    else: raise AssertionError("repeated ARM execution must not inflate science")


def test_executed_unranked_window_is_fatal():
    try:
        score([_baseline()], [_arm(mask=64)], _inputs("ds7-s-v0"))
    except ValueError as error:
        assert "was not ranked" in str(error)
    else: raise AssertionError("unranked execution must fail")


def test_sealed_inputs_require_context_binding_and_all_22_baseline_windows():
    context = {"session_id": "s", "visit_index": 0, "rate_hz": 2_500_000}
    baseline = {"case_id": "ds7-s-v0", "status": "ok", "context": context,
                "result": {"probes": [
                    {"receiver_id": receiver, "probe_start_ms": start, "candidates": []}
                    for receiver in (0, 1) for start in range(0, 101, 10)
                ]}}
    arm = _arm(); arm["context"] = context
    inputs = {"schema": "ds7-large-arm-inputs/v1", "complete": True, "rows": [context]}
    assert score([baseline], [arm], inputs)["windows"]["baseline_total"] == 22
    baseline["result"]["probes"].pop()
    try:
        score([baseline], [arm], inputs)
    except ValueError as error:
        assert "all 22" in str(error)
    else: raise AssertionError("truncated baseline denominator must fail")


def test_arm_requires_exact_receiver_rank_and_candidate_count_contracts():
    arm = _arm(order=(1, 2, 3, 4, 5, 6))
    try:
        score([_baseline()], [arm], _inputs("ds7-s-v0"))
    except ValueError as error:
        assert "permutation" in str(error)
    else: raise AssertionError("shifted rank windows must fail")
    arm = _arm(); arm["receivers"][0]["result"]["confirmations"][0]["candidate_count"] = 2
    try:
        score([_baseline()], [arm], _inputs("ds7-s-v0"))
    except ValueError as error:
        assert "candidate_count" in str(error)
    else: raise AssertionError("candidate count mismatch must fail")
    arm = _arm(); arm["receivers"][1]["receiver"] = 0
    try:
        score([_baseline()], [arm], _inputs("ds7-s-v0"))
    except ValueError as error:
        assert "receiver inventory" in str(error)
    else: raise AssertionError("duplicate receiver must fail")


def test_per_rate_and_exact_margin_boundary_counts_are_reported():
    contexts = [
        {"session_id": "s", "visit_index": 0, "rate_hz": 2_500_000},
        {"session_id": "s", "visit_index": 1, "rate_hz": 5_000_000},
    ]
    baseline = []
    arm = []
    for context in contexts:
        probes = [{"receiver_id": receiver, "probe_start_ms": start, "candidates": [
            {"epoch_sample": 100, "tracking_cfo_hz": 1000., "margin": .025, "passed_margin_gate": True}
        ]} for receiver in (0, 1) for start in range(0, 101, 10)]
        baseline.append({"context": context, "status": "ok", "result": {"probes": probes}})
        item = _arm(case=f"ds7-s-v{context['visit_index']}"); item["context"] = context; arm.append(item)
    inputs = {"schema": "ds7-large-arm-inputs/v1", "complete": True, "rows": contexts}
    report = score(baseline, arm, inputs)
    assert set(report["per_rate"]) == {"2500000", "5000000"}
    assert report["margin_boundary"]["baseline_candidates_margin_exactly_threshold"] == 44


def test_one_to_one_cardinality_matches_frozen_scorer_on_prior_28_original_rows():
    root = Path(__file__).resolve().parents[2]
    frozen_path = root / "reports/2026_09_28_ds7_glrt_benchmark/scoring.py"
    spec = importlib.util.spec_from_file_location("frozen_ds7_scoring", frozen_path)
    frozen = importlib.util.module_from_spec(spec); assert spec.loader is not None
    sys.modules[spec.name] = frozen
    spec.loader.exec_module(frozen)
    rows = [json.loads(line) for line in (root / "reports/2026_09_28_ds7_glrt_benchmark/run-01/rows.jsonl").read_text().splitlines()]
    rows = [row for row in rows if row["method"] == "original"]
    unique = {}
    for row in rows: unique.setdefault(local_score.case_id(row), row)
    rows = list(unique.values())
    assert len(rows) == 28
    for row in rows:
        groups = {}
        for candidate in frozen._candidates(row):
            if candidate.passed_margin_gate: groups.setdefault(candidate.identity, []).append(candidate)
        for candidates in groups.values():
            frozen_count = len(frozen._match_group(candidates, candidates))
            local = [local_score.Candidate("case", item.receiver_id, item.probe_start_ms,
                                           item.epoch_sample, item.tracking_cfo_hz, item.margin, True)
                     for item in candidates]
            assert local_score._maximum_pairs(local, local, candidates[0].rate_hz) == frozen_count
