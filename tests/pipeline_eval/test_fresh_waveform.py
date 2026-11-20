import pytest

from tools.pipeline_eval.qualification import fresh_waveform as trial
from tools.pipeline_eval.qualification import fresh_waveform_results as results


def test_rank_uses_the_frozen_first_manifest_and_excludes_prior_services():
    def capture(case, first, score):
        return dict(id=case, recording={"segments": [{"sha256": first}]}, prior_error=score)

    rows = [
        capture("DS26-5", "ff", 0),
        capture("DS26-1", "01", 20),
        capture("DS26-2", "00", 1),
        capture("DS29-4", "00", 10),
        {"id": "DS26-3"},
    ]
    assert [row["id"] for row in trial.ranked_cases(rows, "DS26", {"DS26-2"})] == [
        "DS26-1",
        "DS26-5",
    ]


def test_fresh_archive_authenticates_detector_content_and_complete_visit_count():
    digest = trial.whole_iq.recording.digest
    manifest, binary = "sha256:" + "a" * 64, "b" * 64
    case = {"clock_authority": manifest, "recording": {"window_count": 2}}
    probes = [{"receiver_id": rx, "candidates": []} for rx in (0, 1)]
    excluded = ["invalid capture"]
    clocks = [{"sequence": 0}, [1, 2], 1234]
    analysis = digest([results.IDENTITY, "sha256:" + binary, manifest, probes, excluded])
    native = dict(
        schema_version=2,
        source=dict(
            session_id="fast-" + "a" * 32,
            input_manifest_sha256=manifest,
            analysis_manifest_sha256=analysis,
            raw_recording_authority_digest="same raw input",
            probes=probes,
        ),
        provenance=dict(
            run_id="replay-" + analysis[7:39],
            detector_sha256="sha256:" + binary,
            excluded_windows=excluded,
            processed_windows=1,
            invalid_capture=1,
        ),
        clock_anchor=clocks[0],
        delivery_clocks=clocks[1],
        last_sample_counter=clocks[2],
    )
    ledger = dict(
        raw_authority="same raw input",
        clock_sha256=digest(clocks),
        excluded_sha256=digest(excluded),
        probes_sha256=digest([{"receiver_id": 0}, {"receiver_id": 1}]),
        dual_calls=1,
    )
    results.validate_native(native, case, ledger, binary)
    with pytest.raises(ValueError):
        results.validate_native(native, case, dict(ledger, dual_calls=0), binary)
    probes[0]["candidates"] = [{"cfo_hz": 10}]
    with pytest.raises(ValueError):
        results.validate_native(native, case, ledger, binary)


def test_failed_waveform_counts_against_each_calibration_arm():
    case = "DS29-0001"
    fit = dict(latlon=[0, 1], status="fix", error_km=1)
    ref = dict(
        truth=[0, 0],
        reference={name: dict.fromkeys(results.ARMS, fit) for name in results.V5_OPTIONS},
    )
    record = dict(
        result=dict(
            status="failed", arms={arm: {"latlon": None} for arm in results.ARMS}, metrics={}
        )
    )
    marks = results.score_rows({case: record}, {case: ref}, {case: {"wall_to_failure_s": 42}})
    assert len(marks) == 10
    attempt = [row for row in marks if row["method"] == trial.METHOD]
    assert {row["arm"] for row in attempt} == set(results.ARMS)
    assert all(row["status"] == "failed" and row["wall_to_failure_s"] == 42 for row in attempt)
    assert all(not row["published"] and not row["within_10pct"] for row in attempt)
