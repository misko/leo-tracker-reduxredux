from __future__ import annotations

from scoring import score


def _candidate(rank=0, epoch=100, cfo=1_000.0, margin=0.03):
    return {
        "candidate_rank": rank,
        "epoch_sample": epoch,
        "acquired_cfo_hz": cfo,
        "residual_cfo_hz": 0.0,
        "tracking_cfo_hz": cfo,
        "exact_score": margin + 0.1,
        "control_score": 0.1,
        "margin": margin,
        "passed_margin_gate": margin >= 0.025,
    }


def _row(*, session="s", visit=0, repeat=0, status="ok", probes=(), rate=2_500_000):
    context = {
        "session_id": session,
        "visit_index": visit,
        "sample_start_counter": visit * 50_000,
        "rate_hz": rate,
        "target_index": 0,
        "target": {"channel": 1, "edge": "lower"},
    }
    return {
        "context": context,
        "status": status,
        "result": None if status == "failed" else {
            "first": None,
            "decision_best_margin": None,
            "full_best_margin": None,
            "reason": "synthetic",
            "probes": list(probes),
        },
        "timing": {"cpu_s": 0.1, "wall_s": 0.2},
        "method": "D",
        "repeat": repeat,
        "diagnostics": {},
    }


def _probe(receiver=0, index=0, start=0, candidates=()):
    return {
        "receiver_id": receiver,
        "probe_index": index,
        "probe_start_ms": start,
        "candidates": list(candidates),
    }


def test_exact_output_and_no_reference_positive_denominator_is_na():
    row = _row(probes=(_probe(candidates=(_candidate(margin=0.01),)),))
    result = score([row], [row])
    assert result["science_equivalence"] == {
        "successful_row_pairs": 1,
        "exact_full_output_equal": 1,
        "exact_full_output_fraction": 1.0,
    }
    assert result["recovery"]["positive_candidate_identity"]["denominator"] == 0
    assert result["recovery"]["positive_candidate_identity"]["fraction"] is None
    assert result["reference_denominators"]["negative_candidates"] == 1


def test_competing_reference_candidates_receive_one_to_one_credit_only():
    reference = _row(probes=(_probe(candidates=(_candidate(rank=0, epoch=100), _candidate(rank=1, epoch=101))),))
    candidate = _row(probes=(_probe(candidates=(_candidate(rank=9, epoch=100),)),))
    result = score([reference], [candidate])
    assert result["matched_candidate_pairs"] == 1
    assert result["recovery"]["positive_candidate_identity"] == {
        "matched": 1, "denominator": 2, "fraction": 0.5
    }


def test_exact_same_positive_hypotheses_reach_the_maximum_matching_cardinality():
    probes = _probe(candidates=(_candidate(rank=0, epoch=100), _candidate(rank=1, epoch=101)))
    result = score([_row(probes=(probes,))], [_row(probes=(probes,))])
    assert result["matched_candidate_pairs"] == 2
    assert result["matched_positive_hypothesis_pairs"] == 2
    assert result["recovery"]["positive_candidate_identity"] == {
        "matched": 2, "denominator": 2, "fraction": 1.0
    }


def test_positive_matching_cannot_be_stolen_by_a_nearer_negative_candidate():
    reference = _row(probes=(_probe(candidates=(_candidate(epoch=100, margin=0.03),)),))
    candidate = _row(probes=(_probe(candidates=(
        _candidate(rank=0, epoch=100, margin=0.01),
        _candidate(rank=1, epoch=102, margin=0.03),
    )),))
    result = score([reference], [candidate])
    assert result["matched_candidate_pairs"] == 1
    assert result["matched_positive_hypothesis_pairs"] == 1
    assert result["recovery"]["positive_candidate_identity"] == {
        "matched": 1, "denominator": 1, "fraction": 1.0
    }


def test_positive_candidate_matched_to_negative_reference_is_reported_separately():
    reference = _row(probes=(_probe(candidates=(_candidate(margin=0.01),)),))
    candidate = _row(probes=(_probe(candidates=(_candidate(margin=0.03),)),))
    result = score([reference], [candidate])
    extras = result["candidate_extras_unmatched_not_false_alarms"]
    assert extras["positive_candidates_associated_with_reference_negative"] == 1
    assert extras["positive_candidates_unmatched_identity"] == 1


def test_failed_candidate_row_is_accounted_as_unprocessed_miss():
    reference = _row(probes=(_probe(candidates=(_candidate(),)),))
    candidate = _row(status="failed")
    result = score([reference], [candidate])
    assert result["row_accounting"]["candidate_failed"] == 1
    assert result["reference_denominators"]["method_unprocessed_positive_candidates"] == 1
    assert result["matched_candidate_pairs"] == 0


def test_association_never_crosses_receiver_probe_session_or_repeat():
    reference = _row(session="reference", probes=(_probe(receiver=0, index=0, candidates=(_candidate(),)),))
    wrong_receiver = _row(session="reference", probes=(_probe(receiver=1, index=0, candidates=(_candidate(),)),))
    other_session = _row(session="other", probes=(_probe(receiver=0, index=0, candidates=(_candidate(),)),))
    other_repeat = _row(session="reference", repeat=1, probes=(_probe(receiver=0, index=0, candidates=(_candidate(),)),))
    result = score([reference], [wrong_receiver, other_session, other_repeat])
    assert result["matched_candidate_pairs"] == 0
    assert result["row_accounting"]["candidate_unmatched_contexts"] == 2
    assert result["candidate_extras_unmatched_not_false_alarms"]["positive_candidates_unmatched_identity"] == 3


def test_standard_nonoverlap_and_cfo_rule_recovers_confirmed_receiver_visit():
    probes = (
        _probe(index=0, start=0, candidates=(_candidate(cfo=1_000.0),)),
        _probe(index=2, start=20, candidates=(_candidate(cfo=7_999.0),)),
    )
    result = score([_row(probes=probes)], [_row(probes=probes)])
    assert result["reference_denominators"]["confirmed_receiver_visit_pairs"] == 1
    assert result["recovery"]["confirmed_receiver_visit_matched_identity"] == {
        "matched": 1, "denominator": 1, "fraction": 1.0
    }


def test_activity_only_confirmation_does_not_credit_an_unmatched_cfo_branch():
    reference = _row(probes=(
        _probe(index=0, start=0, candidates=(_candidate(epoch=100, cfo=0.0),)),
        _probe(index=1, start=20, candidates=(_candidate(epoch=200, cfo=0.0),)),
    ))
    candidate = _row(probes=(
        _probe(index=0, start=0, candidates=(_candidate(epoch=100, cfo=20_000.0),)),
        _probe(index=1, start=20, candidates=(_candidate(epoch=200, cfo=20_000.0),)),
    ))
    result = score([reference], [candidate])
    assert result["recovery"]["confirmed_receiver_visit_activity_only"]["matched"] == 1
    assert result["recovery"]["confirmed_receiver_visit_matched_identity"] == {
        "matched": 0, "denominator": 1, "fraction": 0.0
    }


def test_incomplete_coverage_suppresses_runtime_speedup_and_negative_timing_rejects():
    reference = _row(probes=(_probe(candidates=(_candidate(),)),))
    result = score([reference], [])
    assert result["runtime_seconds"]["complete_coverage"] is False
    assert result["runtime_seconds"]["cpu_speedup_reference_over_candidate"] is None
    invalid = _row(probes=(_probe(candidates=(_candidate(),)),))
    invalid["timing"] = {"cpu_s": -0.1, "wall_s": 0.2}
    try:
        score([invalid], [invalid])
    except ValueError as error:
        assert "cannot be negative" in str(error)
    else:
        raise AssertionError("negative timing must be rejected")
