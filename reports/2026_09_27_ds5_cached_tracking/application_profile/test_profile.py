from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("scanner_application_profile", HERE / "run_profile.py")
assert SPEC and SPEC.loader
PROFILE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROFILE
SPEC.loader.exec_module(PROFILE)


def test_source_lock_uses_repository_science() -> None:
    lock = PROFILE.verify_source_lock()
    assert lock["stage"] == "frozen_before_profile_outcomes"
    root = Path(__file__).resolve().parents[3]
    assert Path(PROFILE.detector.__file__).is_relative_to(root / "src")
    assert Path(PROFILE.pilot_methods.__file__).is_relative_to(root / "src")


def test_metadata_selection_and_application_geometry() -> None:
    selected = PROFILE.select_cases()
    assert [case["case_id"] for case in selected] == [
        "newdev-r2500000-scan-fw-40ebc07665464c7d-v001077",
        "newdev-r5000000-scan-fw-e76c229e9dc498b3-v001077",
    ]
    for case in selected:
        config = PROFILE.configuration(case)
        assert config.scheduled_probe_count == 11
        assert config.receiver_ids == (0, 1)
        assert config.maximum_acquisition_candidates == 10
        assert config.probe_samples == case["rate_hz"] // 50


def test_stage_wrapper_preserves_return_and_restores_function() -> None:
    module = SimpleNamespace(function=lambda value: value + 1)
    original = module.function
    recorder = PROFILE.StageRecorder()
    recorder.patch(module, "function", "stage")
    assert module.function(3) == 4
    recorder.restore()
    assert module.function is original
    summary = recorder.summary()["stage"]
    assert summary["calls"] == 1
    assert summary["inclusive_process_cpu_ms"] >= 0


def test_exact_output_contract_is_complete() -> None:
    first = SimpleNamespace(model_dump=lambda **_kwargs: {"receiver_id": 0, "margin": 0.1})
    result = SimpleNamespace(first=first, best_margin=0.1, reason="complete")
    assert PROFILE.serialized_output(result) == {
        "first": {"receiver_id": 0, "margin": 0.1},
        "best_margin": 0.1,
        "reason": "complete",
    }


def test_profile_result_is_complete_bounded_and_exact() -> None:
    result = PROFILE.load_json(HERE / "results.json")
    assert result["status"] == "complete"
    assert result["fresh_holdout_opened"] is False
    assert result["elapsed_wall_ms"] < 120_000
    assert result["native_backend"] == "avx2_fma"
    assert len(result["rows"]) == 2
    assert all(row["diagnostic_output_exact"] for row in result["rows"])
    for row in result["rows"]:
        assert row["expected_operation_counts"] == {
            "scheduled_probes": 11,
            "receiver_probe_acquisitions": 22,
            "maximum_glrt64_candidate_scores": 220,
            "overlap_reprocessing_factor_per_receiver": 11 / 6,
        }
        assert row["stages"]["acquire_symbolwise"]["calls"] == 22
        assert row["stages"]["conditioned_glrt64_score"]["calls"] == 220
        assert row["stages"]["folded_anchor_score_grid"]["calls"] == 22


def test_measured_stage_inventory_matches_candidate_bound() -> None:
    rows = PROFILE.load_json(HERE / "results.json")["rows"]
    for row in rows:
        assert all(
            item["candidate_count"] == 10
            for item in row["stages"]["acquire_symbolwise"]["metadata"]
        )
        assert row["stages"]["normalized_frame_scores"]["calls"] == 220
        assert row["stages"]["conditioned_frame_scores"]["calls"] == 220
        assert row["stages"]["normalized_frame_score"]["calls"] == 660
        assert row["stages"]["conditioned_correlation_workspace"]["calls"] == 220
        assert row["stages"]["glrt_pair"]["calls"] == 220
