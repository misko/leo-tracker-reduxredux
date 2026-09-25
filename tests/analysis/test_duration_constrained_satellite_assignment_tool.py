from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/evaluate_duration_constrained_satellite_assignment.py"
    spec = importlib.util.spec_from_file_location(
        "evaluate_duration_constrained_satellite_assignment_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


def _fixture(tmp_path: Path, tool: ModuleType) -> tuple[Path, Path]:
    manifest_path = tmp_path / "manifest.json"
    scientific = tmp_path / "scientific"
    scientific.mkdir()
    sample_rate_hz = 2_500_000
    sample_count = 3_000_000
    first_utc_ns = 1_787_599_535_194_390_120
    last_utc_ns = first_utc_ns + 1_199_999_600
    timing = {
        "schema_version": 1,
        "first_sample": {
            "schema_version": 1,
            "estimate_utc_ns": first_utc_ns,
            "earliest_utc_ns": first_utc_ns - 500_000,
            "latest_utc_ns": first_utc_ns + 500_000,
            "method": "device_counter_anchored",
        },
        "last_sample": {
            "schema_version": 1,
            "estimate_utc_ns": last_utc_ns,
            "earliest_utc_ns": last_utc_ns - 600_000,
            "latest_utc_ns": last_utc_ns + 600_000,
            "method": "device_counter_anchored",
        },
    }
    manifest = {
        "schema_version": 2,
        "session_id": tool.TARGET_SESSION_ID,
        "tags": ["tuning:stream-1:ch2:upper"],
        "capture_plan": {
            "profile_revision": {
                "profile": {
                    "lnb_lo_hz": 9_750_000_000,
                    "rf_center_frequency_hz": 11_459_687_500,
                }
            }
        },
        "streams": [
            {
                "stream_id": "stream-1",
                "radio": {"radio_id": "radio_pluto_19f2", "serial": "serial-19f2"},
                "captured_sample_count": sample_count,
                "applied_settings": {
                    "sample_rate_hz": sample_rate_hz,
                    "center_frequency_hz": 1_440_312_500,
                    "receiver_ids": [0, 1],
                },
                "timing": timing,
            }
        ],
    }
    _write(manifest_path, manifest)
    manifest_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    schedule_digest = "sha256:schedule"
    alias_digest = "sha256:alias-map"
    bank_digest = "sha256:dealiased"
    final_digest = "sha256:final"
    branch_id = "sha256:branch"
    component_id = "sha256:component"
    seed_id = "sha256:seed"
    model_id = "sha256:model"
    probes = []
    detections = []
    observations = []
    observation_ids = []
    for index in range(41):
        sample_start = index * 62_500
        probe_id = f"sha256:probe-{index:02d}"
        source_id = tool.canonical_digest(
            {"sample_start": sample_start, "candidate_rank": 0, "method": "glrt64"}
        )
        canonical_id = f"sha256:canonical-{index:02d}"
        probes.append(
            {
                "schema_version": 2,
                "probe_id": probe_id,
                "coarse_window_index": index // 40,
                "subwindow_index": (index // 2) % 20,
                "probe_offset_ms": 0 if index % 2 == 0 else 25,
                "sample_start": sample_start,
                "sample_count": 50_000,
                "time_s": sample_start / sample_rate_hz,
            }
        )
        detections.append(
            {
                "sample_start": sample_start,
                "time_s": sample_start / sample_rate_hz,
                "status": "complete",
                "source_candidate_count": 1,
                "truncated_candidate_count": 0,
                "candidates": [
                    {
                        "rank": 0,
                        "local_epoch_sample": 1_250,
                        "qam_accuracy": 0.8,
                        "scores": [
                            {
                                "method": "glrt64",
                                "tracking_cfo_hz": -20_000.0 - 75.0 * index,
                                "exact_score": 0.6,
                                "control_score": 0.05,
                                "margin": 0.55,
                            }
                        ],
                    }
                ],
            }
        )
        observations.append(
            {
                "observation_id": canonical_id,
                "component_id": component_id,
                "sample_start": sample_start,
                "time_s": sample_start / sample_rate_hz,
                "raw_cfo_hz": -20_000.0 - 75.0 * index,
                "component_cfo_hz": -20_000.0 - 75.0 * index,
                "residue_cfo_hz": -20_000.0 - 75.0 * index,
                "alias_index": 0,
                "source_observation_ids": [source_id],
                "source_trajectory_ids": [seed_id],
            }
        )
        observation_ids.append(canonical_id)

    empty_sample_start = 41 * 62_500
    probes.append(
        {
            "schema_version": 2,
            "probe_id": "sha256:probe-empty",
            "coarse_window_index": 1,
            "subwindow_index": 0,
            "probe_offset_ms": 25,
            "sample_start": empty_sample_start,
            "sample_count": 50_000,
            "time_s": empty_sample_start / sample_rate_hz,
        }
    )
    detections.append(
        {
            "sample_start": empty_sample_start,
            "time_s": empty_sample_start / sample_rate_hz,
            "status": "no_result",
            "source_candidate_count": 0,
            "truncated_candidate_count": 0,
            "candidates": [],
        }
    )

    schedule = {
        "schema_version": 2,
        "algorithm_version": "standard-probe-schedule-v2",
        "sample_rate_hz": sample_rate_hz,
        "probe_ms": 20,
        "source_probe_count": 42,
        "returned_probe_count": 42,
        "truncated_probe_count": 0,
        "schedule_digest": schedule_digest,
        "probes": probes,
    }
    scan = {
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
        "probe_schedule_digest": schedule_digest,
        "probe_samples": 50_000,
        "detections": detections,
    }
    alias_map = {
        "schema_version": 2,
        "algorithm_version": "cfo-alias-map-v2",
        "content_digest": alias_digest,
        "alias_spacing_numerator_hz": 2_500_000,
        "alias_spacing_denominator": 11,
        "members": [
            {"trajectory_id": seed_id, "component_id": component_id, "relative_alias_index": 0}
        ],
        "components": [
            {
                "component_id": component_id,
                "trajectory_ids": [seed_id],
                "status": "resolved",
            }
        ],
    }
    canonical_coefficients = [-3_000.0, -20_000.0]
    bank = {
        "schema_version": 4,
        "algorithm_version": "hough-seeded-huber-linear-bank-v4",
        "content_digest": bank_digest,
        "alias_map_digest": alias_digest,
        "observations": observations,
        "branches": [
            {
                "branch_id": branch_id,
                "component_id": component_id,
                "seed_trajectory_id": seed_id,
                "observation_ids": observation_ids,
                "start_s": 0.0,
                "end_s": 1.0,
                "model": {
                    "model_id": model_id,
                    "polynomial_degree": 1,
                    "reference_time_s": 0.0,
                    "coefficients_hz": canonical_coefficients,
                    "residual_rms_hz": 50.0,
                },
            }
        ],
    }
    alias_spacing = 2_500_000 / 11
    final = {
        "schema_version": 3,
        "algorithm_version": "final-trajectory-bank-v3",
        "content_digest": final_digest,
        "dealiased_bank_digest": bank_digest,
        "trajectories": [
            {
                "trajectory_id": "sha256:lift-0",
                "branch_id": branch_id,
                "component_id": component_id,
                "canonical_model_id": model_id,
                "observation_ids": observation_ids,
                "alias_index": 0,
                "canonical_coefficients_hz": canonical_coefficients,
                "absolute_coefficients_hz": canonical_coefficients,
                "automatic_correction_eligible": True,
                "replay_tier": "automatic",
            },
            {
                "trajectory_id": "sha256:lift-1",
                "branch_id": branch_id,
                "component_id": component_id,
                "canonical_model_id": model_id,
                "observation_ids": observation_ids,
                "alias_index": 1,
                "canonical_coefficients_hz": canonical_coefficients,
                "absolute_coefficients_hz": [-3_000.0, -20_000.0 + alias_spacing],
                "automatic_correction_eligible": True,
                "replay_tier": "automatic",
            },
        ],
    }
    segments = {
        "schema_version": 1,
        "algorithm_version": "standard-pilot-doppler-segments-v1",
        "dealiased_bank_digest": bank_digest,
        "final_trajectory_bank_digest": final_digest,
        "source_track_count": 2,
        "analyzed_track_count": 1,
        "truncated_track_count": 1,
        "analyzed_segment_count": 1,
        "qualified_segment_count": 1,
        "absolute_carrier_phase_resolved": False,
        "frame_timing_is_receiver_relative": True,
        "segments": [
            {
                "source_branch_id": branch_id,
                "source_trajectory_id": "sha256:lift-0",
                "source_probe_sample_start": 0,
                "start_time_s": 0.0,
                "end_time_s": 0.075,
                "qualified": True,
                "supported_frame_count": 55,
                "lattice_frame_count": 55,
                "supported_frame_fraction": 1.0,
                "frequency_line_rms_hz": 30.0,
            }
        ],
    }
    path_report = {
        "schema_version": 2,
        "algorithm_version": "standard-path-report-v2",
        "raw_report": {
            "session_id": tool.TARGET_SESSION_ID,
            "stream_id": "stream-1",
            "radio_id": "radio_pluto_19f2",
            "receiver_id": 1,
            "manifest_digest": manifest_digest,
            "sample_rate_hz": sample_rate_hz,
            "declared_sample_count": sample_count,
            "observed_sample_count": sample_count,
            "coverage_fraction": 1.0,
            "probe_schedule_digest": schedule_digest,
            "frequency_reference": {
                "schema_version": 1,
                "reference": "uncalibrated_prior",
                "center_frequency_hz": None,
                "uncertainty_hz": None,
                "calibration_digest": None,
            },
            "timing": {
                "schema_version": 1,
                "first_estimate_utc_ns": timing["first_sample"]["estimate_utc_ns"],
                "first_earliest_utc_ns": timing["first_sample"]["earliest_utc_ns"],
                "first_latest_utc_ns": timing["first_sample"]["latest_utc_ns"],
                "last_estimate_utc_ns": timing["last_sample"]["estimate_utc_ns"],
                "last_earliest_utc_ns": timing["last_sample"]["earliest_utc_ns"],
                "last_latest_utc_ns": timing["last_sample"]["latest_utc_ns"],
            },
        },
    }
    documents = {
        "standard.probe-schedule.v2.json": schedule,
        "standard.pilot-scan.v3.json": scan,
        "standard.cfo-alias-map.v2.json": alias_map,
        "standard.dealiased-trajectory-bank.v4.json": bank,
        "standard.final-trajectory-bank.v3.json": final,
        "standard.pilot-doppler-segments.v1.json": segments,
        "standard.path-report.v2.json": path_report,
    }
    for name, document in documents.items():
        _write(scientific / name, document)
    return manifest_path, scientific


def test_extraction_preserves_probe_identity_and_collapses_constant_cfo_lifts(
    tmp_path: Path,
) -> None:
    tool = _tool()
    manifest, scientific = _fixture(tmp_path, tool)

    result = tool.build_dataset(
        recording_manifest_path=manifest,
        scientific_root=scientific,
    )

    assert result["frequency_binding"]["sky_frequency_hz"] == 11_190_312_500
    assert result["frequency_binding"]["profile_nominal_matches_applied"] is False
    assert result["alias_collapse"]["final_trajectory_hypothesis_count"] == 2
    assert result["alias_collapse"]["deduplicated_branch_count"] == 1
    assert result["duration_constraint_summary"]["dense_20ms_probe_run_span_pass_branch_count"] == 1
    assert (
        result["duration_constraint_summary"]["dense_20ms_integrated_support_pass_branch_count"]
        == 0
    )
    assert result["duration_constraint_summary"]["qualified_frame_run_pass_branch_count"] == 0
    assert result["probe_geometry"]["scheduled_probe_count"] == 42
    assert result["probe_geometry"]["scheduled_usable_probe_count"] == 42
    assert result["probe_geometry"]["scheduled_empty_candidate_probe_count"] == 1
    assert result["scheduled_probes"][-1]["probe_id"] == "sha256:probe-empty"
    assert result["scheduled_probes"][-1]["usable_for_activity"] is True
    assert result["scheduled_probes"][-1]["retained_candidate_count"] == 0
    branch = result["branches"][0]
    assert branch["alias_hypothesis_count"] == 2
    assert branch["source_probe_count"] == 41
    assert branch["observations"][0]["probe_id"] == "sha256:probe-00"
    assert branch["observations"][0]["branch_id"] == "sha256:branch"
    assert branch["observations"][0]["seed_trajectory_id"] == "sha256:seed"
    assert branch["observations"][0]["source_trajectory_ids"] == ["sha256:seed"]
    assert branch["observations"][0]["final_trajectory_ids"] == [
        "sha256:lift-0",
        "sha256:lift-1",
    ]
    assert branch["observations"][0]["measurement_time_s"] == pytest.approx(0.0005)
    assert (
        branch["observations"][0]["measurement_utc"]["estimate_utc_ns"]
        > (result["timing_binding"]["first_estimate_utc_ns"])
    )
    assert branch["minimum_duration_evidence"]["dense_20ms_probe_run_span_pass"] is True
    assert branch["minimum_duration_evidence"]["dense_20ms_integrated_support_pass"] is False
    assert branch["minimum_duration_evidence"]["qualified_frame_run_pass"] is False
    assert branch["minimum_duration_evidence"]["conclusion"] == (
        "candidate_support_only_frame_evidence_incomplete"
    )


def test_extraction_rejects_a_lift_that_changes_doppler_rate(tmp_path: Path) -> None:
    tool = _tool()
    manifest, scientific = _fixture(tmp_path, tool)
    final_path = scientific / "standard.final-trajectory-bank.v3.json"
    final = json.loads(final_path.read_text(encoding="utf-8"))
    final["trajectories"][1]["absolute_coefficients_hz"][0] = -2_999.0
    _write(final_path, final)

    with pytest.raises(ValueError, match="changes Doppler-rate coefficients"):
        tool.build_dataset(recording_manifest_path=manifest, scientific_root=scientific)


def test_extraction_accepts_generic_tuning_channel_and_edge(tmp_path: Path) -> None:
    tool = _tool()
    manifest_path, scientific = _fixture(tmp_path, tool)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tags"] = ["tuning:stream-1:ch3:lower"]
    _write(manifest_path, manifest)
    manifest_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    path_report_path = scientific / "standard.path-report.v2.json"
    path_report = json.loads(path_report_path.read_text(encoding="utf-8"))
    path_report["raw_report"]["manifest_digest"] = manifest_digest
    _write(path_report_path, path_report)

    result = tool.build_dataset(
        recording_manifest_path=manifest_path,
        scientific_root=scientific,
    )

    assert result["frequency_binding"]["tuning_tag"] == "tuning:stream-1:ch3:lower"


def _empty_no_result_without_frame_receipt(tmp_path: Path, tool: ModuleType) -> tuple[Path, Path]:
    manifest, scientific = _fixture(tmp_path, tool)
    scan_path = scientific / "standard.pilot-scan.v3.json"
    scan_digest = "sha256:" + hashlib.sha256(scan_path.read_bytes()).hexdigest()

    alias_path = scientific / "standard.cfo-alias-map.v2.json"
    alias_map = json.loads(alias_path.read_text(encoding="utf-8"))
    alias_map.update(
        {
            "status": "no_result",
            "members": [],
            "components": [],
            "component_count": 0,
            "source_representative_count": 0,
            "returned_representative_count": 0,
            "truncated_representative_count": 0,
            "pilot_scan_digest": scan_digest,
        }
    )
    _write(alias_path, alias_map)

    bank_path = scientific / "standard.dealiased-trajectory-bank.v4.json"
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    bank.update(
        {
            "status": "no_result",
            "branches": [],
            "observations": [],
            "source_branch_count": 0,
            "returned_branch_count": 0,
            "truncated_branch_count": 0,
            "source_observation_count": 0,
            "returned_observation_count": 0,
            "truncated_observation_count": 0,
        }
    )
    _write(bank_path, bank)

    final_path = scientific / "standard.final-trajectory-bank.v3.json"
    final = json.loads(final_path.read_text(encoding="utf-8"))
    final.update(
        {
            "status": "no_result",
            "trajectories": [],
            "source_trajectory_count": 0,
            "returned_trajectory_count": 0,
            "truncated_trajectory_count": 0,
        }
    )
    _write(final_path, final)

    report_path = scientific / "standard.path-report.v2.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.update(
        {
            "status": "no_result",
            "final_trajectories": [],
            "source_trajectory_count": 0,
            "returned_trajectory_count": 0,
            "truncated_trajectory_count": 0,
            "cfo_alias_map_digest": alias_map["content_digest"],
            "dealiased_trajectory_bank_digest": bank["content_digest"],
            "final_trajectory_bank_digest": final["content_digest"],
        }
    )
    _write(report_path, report)
    (scientific / "standard.pilot-doppler-segments.v1.json").unlink()
    return manifest, scientific


def test_missing_frame_receipt_is_opt_in_and_fail_closed(tmp_path: Path) -> None:
    tool = _tool()
    manifest, scientific = _empty_no_result_without_frame_receipt(tmp_path, tool)

    with pytest.raises(ValueError, match="frame-segment source product is missing"):
        tool.build_dataset(recording_manifest_path=manifest, scientific_root=scientific)

    result = tool.build_dataset(
        recording_manifest_path=manifest,
        scientific_root=scientific,
        allow_missing_empty_no_result_frame_segments=True,
    )

    assert result["branches"] == []
    assert result["source_completeness"] == {
        "raw_activity_inventory_complete": True,
        "frame_evidence_available": False,
        "missing_source_products": ["standard.pilot-doppler-segments.v1.json"],
    }
    assert result["frame_evidence_inventory"]["frame_evidence_available"] is False
    assert result["frame_evidence_inventory"]["evidence_complete"] is False
    assert "frame_segments" not in result["source_products"]


@pytest.mark.parametrize(
    ("filename", "field", "value", "message"),
    [
        (
            "standard.cfo-alias-map.v2.json",
            "status",
            "complete",
            "empty no-result alias map",
        ),
        (
            "standard.dealiased-trajectory-bank.v4.json",
            "truncated_observation_count",
            1,
            "empty no-result dealiased bank",
        ),
        (
            "standard.final-trajectory-bank.v3.json",
            "returned_trajectory_count",
            1,
            "empty no-result final bank",
        ),
        (
            "standard.path-report.v2.json",
            "status",
            "complete",
            "empty no-result path report",
        ),
    ],
)
def test_missing_frame_receipt_refuses_nonconclusive_lineage(
    tmp_path: Path,
    filename: str,
    field: str,
    value: object,
    message: str,
) -> None:
    tool = _tool()
    manifest, scientific = _empty_no_result_without_frame_receipt(tmp_path, tool)
    path = scientific / filename
    document = json.loads(path.read_text(encoding="utf-8"))
    document[field] = value
    _write(path, document)

    with pytest.raises(ValueError, match=message):
        tool.build_dataset(
            recording_manifest_path=manifest,
            scientific_root=scientific,
            allow_missing_empty_no_result_frame_segments=True,
        )


def test_missing_frame_receipt_refuses_incomplete_pilot_inventory(tmp_path: Path) -> None:
    tool = _tool()
    manifest, scientific = _empty_no_result_without_frame_receipt(tmp_path, tool)
    scan_path = scientific / "standard.pilot-scan.v3.json"
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    scan["detections"][0]["truncated_candidate_count"] = 1
    _write(scan_path, scan)
    alias_path = scientific / "standard.cfo-alias-map.v2.json"
    alias_map = json.loads(alias_path.read_text(encoding="utf-8"))
    alias_map["pilot_scan_digest"] = "sha256:" + hashlib.sha256(scan_path.read_bytes()).hexdigest()
    _write(alias_path, alias_map)

    with pytest.raises(ValueError, match="complete pilot candidate accounting"):
        tool.build_dataset(
            recording_manifest_path=manifest,
            scientific_root=scientific,
            allow_missing_empty_no_result_frame_segments=True,
        )


def test_qnap_output_is_refused() -> None:
    tool = _tool()

    with pytest.raises(ValueError, match="refuses output"):
        tool._refuse_qnap_output(Path("/mnt/qnap01/research/result.json"))
