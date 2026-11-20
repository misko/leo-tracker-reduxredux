from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import native_winner_trial as trial
from tools.pipeline_eval.qualification.full_v5_check import ALIAS_HZ, factor_candidate
from tools.pipeline_eval.variants import native_winner


def candidate(rank, margin, *, epoch=20, cfo=135_000, offset=0.1):
    return factor_candidate(
        rank,
        epoch,
        status="complete",
        offset=offset,
        cfo=cfo,
        exact=margin + 0.032,
        control=0.032,
        margin=margin,
    )


def document(probes):
    return dict(
        schema_version=2,
        clock_anchor=dict(sample_counter=100),
        delivery_clocks=[dict(monotonic_ns=10)],
        last_sample_counter=600_100,
        source=dict(
            session_id="test",
            sample_rate_hz=10_000_000,
            analysis_manifest_sha256="raw",
            probes=probes,
        ),
        provenance=dict(
            run_id="replay-raw",
            scope="complete recordings",
            window_count=3,
            processed_windows=2,
            invalid_capture=1,
            excluded_windows=[dict(visit=2, reason="retune")],
        ),
    )


def probe(visit, receiver, candidates):
    return dict(
        visit_index=visit,
        receiver_id=receiver,
        channel=3 + visit,
        valid_start_counter=200_000 * visit + 100,
        candidates=candidates,
    )


def test_gate_keeps_the_original_candidate_and_uses_rank_for_ties():
    first = candidate(2, 0.060)
    other = candidate(3, 0.060)
    strongest = candidate(7, 0.2)
    assert native_winner.select_candidate([other, first]) is first
    assert native_winner.select_candidate([first, other, strongest]) is strongest
    assert native_winner.select_candidate([first, candidate(0, 0.0599)]) is first
    assert native_winner.select_candidate([candidate(0, 0.0599)]) is None
    assert native_winner.select_candidate([]) is None


def test_document_retains_timing_probe_support_and_capture_exclusions():
    kept = candidate(1, 0.250)
    raw = document([probe(0, 0, [kept, candidate(0, 0.050)]), probe(1, 1, [])])
    unchanged = deepcopy(raw)
    derived = native_winner.apply_document(raw)
    assert raw == unchanged
    assert native_winner.apply_document(raw) == derived
    assert derived["source"]["probes"] == [probe(0, 0, [kept]), probe(1, 1, [])]
    assert derived["clock_anchor"] == raw["clock_anchor"]
    assert derived["delivery_clocks"] == raw["delivery_clocks"]
    assert derived["last_sample_counter"] == raw["last_sample_counter"]
    assert derived["provenance"]["excluded_windows"] == raw["provenance"]["excluded_windows"]
    assert (
        derived["source"]["analysis_manifest_sha256"] != raw["source"]["analysis_manifest_sha256"]
    )
    assert derived["provenance"]["run_id"] != raw["provenance"]["run_id"]


def test_detector_audit_distinguishes_alias_matches_nulls_and_lost_proposals():
    a = probe(0, 0, [candidate(0, 0.1, epoch=13_332)])
    b = probe(1, 0, [candidate(0, 0.1)])
    null = probe(1, 1, [])
    reference = document([a, b, null])
    raw = document(
        [
            dict(a, candidates=[candidate(0, 0.2, epoch=0, cfo=135_000 + ALIAS_HZ + 30)]),
            dict(b, candidates=[candidate(0, 0.2, epoch=1000)]),
            dict(null, candidates=[candidate(0, 0.040)]),
        ]
    )
    calibrated = native_winner.apply_document(raw)
    result = trial.compare(reference, raw, calibrated)
    assert result["native"]["overall"] == dict(
        matched=1,
        changed_winner=1,
        reference_positive_only=0,
        native_positive_only=1,
        both_null=0,
        oracle_complete=1,
        oracle_stock_gate=1,
        probes=3,
        reference_positive=2,
        native_positive=3,
        matched_f1=0.4,
    )
    assert result["calibrated"]["overall"]["both_null"] == 1
    assert result["calibrated"]["matched_alias_branch_changes"] == 1
    assert result["calibrated"]["matched_absolute_aliased_cfo_delta_hz"]["p50"] == pytest.approx(30)


def test_detector_audit_rejects_changed_sample_support():
    a = probe(0, 0, [candidate(0, 0.1)])
    reference = document([a])
    raw = document([dict(a, valid_start_counter=200)])
    with pytest.raises(ValueError, match="captured sample support"):
        trial.compare(reference, raw, native_winner.apply_document(raw))


def test_recipe_matches_calibration_seal():
    receipt = trial._seal()
    assert receipt["calibration_case"] == "DS26-0036"
    assert receipt["minimum_margin"] == native_winner.MINIMUM_MARGIN
