"""Reporting checks use synthetic truth and never launch inference."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "report_dataset", Path(__file__).with_name("report_dataset.py")
)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def terminal():
    original = {
        "endpoint_latlon": [0.0, 0.01],
        "RMS_hz": 80.0,
        "negative_twice_elbo": 100.0,
        "associated_ids": ["old"],
        "owners": {"old": 12},
    }
    published = {
        "endpoint_latlon": [0.0, 0.02],
        "negative_twice_elbo": 120.0,
        "associated_ids": ["old", "accepted"],
        "owners": {"old": 12, "accepted": 13},
    }
    return {
        "state": "complete",
        "baseline": {"arms": {a: copy.deepcopy(original) for a in report.ARMS}},
        "selected": {"arms": {a: copy.deepcopy(published) for a in report.ARMS}},
        "read_audit": {"verified": True},
        "decision": "ALGO03_single",
        "total_seconds": 99.0,
    }


def new_selection(old):
    selected = copy.deepcopy(old["selected"])
    for value in selected["arms"].values():
        value["owners"]["new"] = 14
        value["associated_ids"].append("new")
        value["endpoint_latlon"] = [0.0, 0.015]
    return selected


def make_rows(old, outcome=None, decision=None):
    return report.build_case_rows(
        {"case": "DS26-TEST"},
        {"state": "complete"},
        outcome,
        old,
        [0.0, 0.0],
        {"old", "accepted", "new"},
        decision,
    )


def test_baseline_is_published_algo03_not_embedded_algo02_or_raw_worker():
    old = terminal()
    raw = new_selection(old)
    outcome = {"accepted_update": False, "selected": old["selected"], "baseline": old["baseline"]}
    rows = make_rows(old, outcome, {"selected": raw, "decision": "ALGO03_single"})
    assert all(r["baseline_associated"] == r["candidate_associated"] == 2 for r in rows)
    assert all(r["baseline_longitude_deg"] == r["candidate_longitude_deg"] == 0.02 for r in rows)
    assert all(r["raw_worker_selected"] and not r["accepted_update"] for r in rows)


def test_replay_failure_keeps_exact_published_algo03_position_and_owners():
    old = terminal()
    rows = report.build_case_rows(
        {"case": "DS26-TEST"},
        {"state": "replay_failed"},
        None,
        old,
        [0.0, 0.0],
        {"old", "accepted", "new"},
    )
    assert all(r["baseline_error_km"] == r["candidate_error_km"] for r in rows)
    assert all(r["added_associated"] == 0 and r["lost_associated"] == 0 for r in rows)


def test_historical_read_guard_failure_cannot_accept_new_owner():
    old = terminal()
    old["read_audit"]["verified"] = False
    raw = new_selection(old)
    outcome = {"accepted_update": True, "selected": raw, "baseline": old["baseline"]}
    with pytest.raises(ValueError, match="Historically unverified"):
        make_rows(old, outcome, {"selected": raw})


def test_additive_gate_rejects_owner_replacement_even_when_point_count_increases():
    old = terminal()
    raw = new_selection(old)
    raw["arms"]["c0"]["owners"]["old"] = 99
    outcome = {"accepted_update": True, "selected": raw, "baseline": old["baseline"]}
    with pytest.raises(ValueError, match="loses or changes"):
        make_rows(old, outcome, {"selected": raw})


def test_accepted_addition_and_paired_summary_use_full_observation_denominator():
    old = terminal()
    raw = new_selection(old)
    outcome = {"accepted_update": True, "selected": raw, "baseline": old["baseline"]}
    rows = make_rows(old, outcome, {"selected": raw})
    unavailable = report.build_case_rows(
        {"case": "DS26-UNAVAILABLE"},
        {"state": "unavailable", "reason": "no_existing_public_GLRT_input"},
        None,
        None,
        [0.0, 0.0],
    )
    summary = report.summarize(rows + unavailable)
    for value in summary.values():
        assert value["full_scan_denominator"] == 2
        assert value["paired_complete"] == 1
        assert value["verified_GLRT_observations"] == 3
        assert value["baseline_associated"] == 2 and value["candidate_associated"] == 3
        assert value["improvements"] == 1


def test_every_positive_error_change_is_retained_as_regression():
    old = terminal()
    raw = new_selection(old)
    for value in raw["arms"].values():
        value["endpoint_latlon"] = [0.0, 0.025]
    outcome = {"accepted_update": True, "selected": raw, "baseline": old["baseline"]}
    summary = report.summarize(make_rows(old, outcome, {"selected": raw}))
    assert all(len(s["regressions"]) == 1 for s in summary.values())


def test_identical_accepted_cached_candidate_is_not_counted_as_an_actual_change():
    old = terminal()
    outcome = {"accepted_update": True, "selected": old["selected"], "baseline": old["baseline"]}
    rows = make_rows(old, outcome, {"selected": old["selected"]})
    for summary in report.summarize(rows).values():
        assert summary["accepted_update_cases"] == 1
        assert summary["actually_changed_cases"] == 0
        assert summary["accepted_identical_cached_candidates"] == 1


def test_frequency_objective_delta_is_not_compared_when_owners_or_ids_change():
    old = terminal()
    raw = new_selection(old)
    outcome = {"accepted_update": True, "selected": raw, "baseline": old["baseline"]}
    for summary in report.summarize(make_rows(old, outcome, {"selected": raw})).values():
        assert summary["frequency_fit_changes"]["exact_ID_and_owner_pairs"] == 0
        assert summary["frequency_fit_changes"]["support_changed_not_comparable"] == 1
        assert summary["frequency_fit_changes"]["frequency_objective"]["paired_scans"] == 0


def test_seal_missing_or_incomplete_blocks_reporting_before_truth(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"cases": [dict(case="DS26-TEST", recording_format="short_window_iq_recording")]}
        )
    )
    (tmp_path / "dataset-protocol.json").write_text(
        json.dumps(
            {
                "source_manifest": str(manifest),
                "manifest_sha256": report.sha(manifest),
                "fast_cases": ["DS26-TEST"],
            }
        )
    )
    with pytest.raises(FileNotFoundError):
        report.verify_study(tmp_path, expected_cases=1)
    (tmp_path / "final-dataset-seal.json").write_text(
        json.dumps({"no_GPS_inference": True, "completed_before_reporting": False})
    )
    with pytest.raises(ValueError, match="sealed before reporting"):
        report.verify_study(tmp_path, expected_cases=1)


def test_tampered_source_hash_blocks_report(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text("{}")
    expected = report.sha(path)
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="Hash mismatch"):
        report.check_hash(path, expected)


def sealed_unavailable_study(tmp_path):
    member = dict(case="DS26-TEST", recording_format="short_window_iq_recording")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"cases": [member]}))
    (tmp_path / "dataset-protocol.json").write_text(
        json.dumps(
            {
                "source_manifest": str(manifest),
                "manifest_sha256": report.sha(manifest),
                "fast_cases": [member["case"]],
            }
        )
    )
    scientific_source = tmp_path / "science.py"
    scientific_source.write_text("# frozen scientific source\n")
    freeze = tmp_path / "source-freeze.json"
    freeze.write_text(
        json.dumps({"files_sha256": {str(scientific_source): report.sha(scientific_source)}})
    )
    folder = tmp_path / "cases" / member["case"]
    folder.mkdir(parents=True)
    receipt = folder / "receipt.json"
    receipt.write_text(json.dumps({"case": member["case"], "state": "unavailable"}))
    (tmp_path / "final-dataset-seal.json").write_text(
        json.dumps(
            {
                "receipt_sha256": {member["case"]: report.sha(receipt)},
                "no_GPS_inference": True,
                "completed_before_reporting": True,
                "source_freeze_sha256": report.sha(freeze),
            }
        )
    )
    return receipt


def test_global_seal_includes_unavailable_case_without_inventing_an_inference_endpoint(tmp_path):
    sealed_unavailable_study(tmp_path)
    _, verified = report.verify_study(tmp_path, expected_cases=1)
    assert len(verified) == 1
    assert verified[0][1]["state"] == "unavailable"
    assert verified[0][2] is None


def test_global_seal_detects_receipt_modification(tmp_path):
    receipt = sealed_unavailable_study(tmp_path)
    receipt.write_text(json.dumps({"case": "DS26-TEST", "state": "complete"}))
    with pytest.raises(ValueError, match="Hash mismatch"):
        report.verify_study(tmp_path, expected_cases=1)


def test_baseline_checkpoint_rejects_wrong_published_association_count():
    summary = {
        "c0": {
            "paired_complete": 148,
            "verified_GLRT_observations": 650404,
            "baseline_associated": 461709,
        },
        "fitted_c": {},
    }
    with pytest.raises(ValueError, match="baseline denominator or association"):
        report.verify_baseline_checkpoint(summary)


def test_baseline_checkpoint_accepts_exact_published_checkpoint_and_rejects_position_drift():
    summary = {}
    for arm, values in {
        "c0": (1.324560277020008, 0.9932431466984788, 3.562466683815054),
        "fitted_c": (1.3072234606062052, 1.0099691118803937, 3.5506537870301305),
    }.items():
        summary[arm] = dict(
            paired_complete=148,
            verified_GLRT_observations=650404,
            baseline_associated=461708,
            baseline=dict(zip(("mean_km", "median_km", "p95_km"), values, strict=True)),
        )
    report.verify_baseline_checkpoint(summary)
    summary["c0"]["baseline"]["mean_km"] += 0.001
    with pytest.raises(ValueError, match="position checkpoint changed"):
        report.verify_baseline_checkpoint(summary)


def test_worker_attempts_and_stages_capture_budget_omissions_and_uncached_exceptions():
    decision = {
        "attempts": [
            dict(track_id="a", points=20, status="RF_qualified"),
            dict(track_id="b", points=30, status="discovery_budget_exhausted"),
            dict(track_id="c", points=40, status="inclusion_execution_failed"),
        ],
        "stages": [
            dict(name="target-0-annotation", status="complete"),
            dict(name="target-0-inclusion", status="failed", error="OSError: incomplete receipt"),
            dict(name="target-2-inclusion", status="budget_exhausted"),
            dict(name="joint-probe", status="budget_exhausted"),
            dict(name="control-c0", status="failed", error="TimeoutExpired: timed out"),
        ],
    }
    work = report.work_accounting(
        decision,
        {"completed_target_ids": ["a", "b", "c", "d"]},
        [{"script": "annotation", "reused": True}],
    )
    assert work["original_completed_target_schedule"] == 4
    assert work["actual_attempts"] == 3
    assert work["original_scheduled_targets_not_attempted"] == 1
    assert work["targets_with_completed_scientific_decision"] == 1
    assert work["targets_with_RF_inclusion_decision"] == 1
    assert work["discovery_budget_exhausted_targets"] == 1
    assert work["budget_limited_targets"] == 2
    assert work["budget_limited_target_points"] == 70
    assert work["budget_exhausted_stages"] == 2
    assert work["failed_stages"] == 2
    assert work["explicit_timeout_error_stages"] == 1
    assert work["executed_stage_receipt_gap"] == 2
    assert len(work["failure_or_budget_stages"]) == 4


def test_completed_annotation_rejection_is_a_scientific_decision_not_a_budget_omission():
    work = report.work_accounting(
        {
            "attempts": [
                dict(track_id="a", status="ambiguous_identity", points=24),
                dict(track_id="b", status="RF_rejected", points=30),
            ],
            "stages": [],
        },
        {"completed_target_ids": ["a", "b"]},
    )
    assert work["targets_with_completed_scientific_decision"] == 2
    assert work["targets_with_RF_inclusion_decision"] == 1
    assert work["budget_limited_targets"] == 0


def test_aggregate_work_retains_status_counts_and_full_case_denominator():
    complete = report.work_accounting(
        {
            "attempts": [dict(track_id="a", status="discovery_budget_exhausted", points=20)],
            "stages": [],
        },
        {"completed_target_ids": ["a"]},
    )
    complete.update(case="DS26-ONE", has_worker_decision=True)
    unavailable = report.work_accounting(None)
    unavailable.update(case="DS26-TWO", has_worker_decision=False)
    aggregate = report.aggregate_work([complete, unavailable])
    assert aggregate["case_count"] == 2
    assert aggregate["cases_with_worker_decision"] == 1
    assert aggregate["actual_attempts"] == 1
    assert aggregate["attempt_status_counts"] == {"discovery_budget_exhausted": 1}
    assert aggregate["budget_limited_cases"] == ["DS26-ONE"]
