from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/calibrate_raw_pilot_activity_scores.py"
    spec = importlib.util.spec_from_file_location("calibrate_raw_pilot_activity_scores_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _null_scan(margins: list[float], schedule_digit: str) -> dict[str, Any]:
    detections = []
    for index, margin in enumerate(margins):
        detections.append(
            {
                "sample_start": index * 100,
                "status": "complete",
                "source_candidate_count": 1,
                "truncated_candidate_count": 0,
                "candidates": [
                    {
                        "rank": 0,
                        "local_epoch_sample": 10,
                        "acquired_cfo_hz": 1_000.0 + index,
                        "scores": [
                            {
                                "method": "glrt64",
                                "exact_score": margin + 0.05,
                                "control_score": 0.05,
                                "margin": margin,
                                "tracking_cfo_hz": 1_000.0 + index,
                            }
                        ],
                    }
                ],
            }
        )
    return {
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
        "maximum_scored_candidates_per_probe": 10,
        "probe_schedule_digest": "sha256:" + schedule_digit * 64,
        "detections": detections,
    }


def _observation(
    *,
    branch_id: str,
    component_id: str,
    source_id: str,
    probe_index: int,
    margin: float,
) -> dict[str, Any]:
    return {
        "branch_id": branch_id,
        "component_id": component_id,
        "source_observation_id": source_id,
        "source_observation_ids": [source_id],
        "probe_id": f"probe-{probe_index}",
        "candidate_rank": 0,
        "probe_sample_start": probe_index * 100,
        "local_epoch_sample": probe_index + 1,
        "glrt64_exact_score": margin + 0.05,
        "glrt64_control_score": 0.05,
        "glrt64_margin": margin,
        "source_tracking_cfo_hz": 1_000.0 + probe_index,
    }


def _duration_input(pilot_scan_digest: str) -> tuple[dict[str, Any], str]:
    component_id = "component-positive"
    first = _observation(
        branch_id="branch-a",
        component_id=component_id,
        source_id="source-a",
        probe_index=0,
        margin=0.2,
    )
    return (
        {
            "schema": "org.leo.research.duration-constrained-satellite-assignment-input/v1",
            "candidate_only": True,
            "satellite_specificity_claimed": False,
            "capture": {
                "declared_sample_count": 1_000,
                "observed_sample_count": 1_000,
                "coverage_fraction": 1.0,
            },
            "source_products": {
                "scan": {
                    "path": "/frozen/source/standard.pilot-scan.v3.json",
                    "file_digest": pilot_scan_digest,
                }
            },
            "scheduled_probes": [
                {
                    "probe_id": f"probe-{index}",
                    "probe_sample_start": index * 100,
                    "source_candidate_count": 1,
                    "retained_candidate_count": 1,
                    "truncated_candidate_count": 0,
                }
                for index in range(3)
            ],
            "frame_evidence_inventory": {
                "evidence_complete": True,
                "alias_expanded_truncated_track_count": 0,
            },
            "alias_components": [
                {
                    "component_id": component_id,
                    "status": "resolved",
                    "branch_ids": ["branch-a", "branch-b"],
                    "deduplicated_source_probe_count": 3,
                }
            ],
            "branches": [
                {
                    "branch_id": "branch-a",
                    "component_id": component_id,
                    "observations": [
                        first,
                        _observation(
                            branch_id="branch-a",
                            component_id=component_id,
                            source_id="source-b",
                            probe_index=1,
                            margin=0.05,
                        ),
                    ],
                },
                {
                    "branch_id": "branch-b",
                    "component_id": component_id,
                    "observations": [
                        {**first, "branch_id": "branch-b"},
                        _observation(
                            branch_id="branch-b",
                            component_id=component_id,
                            source_id="source-c",
                            probe_index=2,
                            margin=0.1,
                        ),
                    ],
                },
            ],
        },
        component_id,
    )


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    null_a = _write(
        tmp_path / "null-a.json",
        _null_scan([0.2, 0.05, 0.1, *([0.0] * 30)], "a"),
    )
    null_b = _write(
        tmp_path / "null-b.json",
        _null_scan([0.0, 0.09, 0.8, *([0.0] * 30)], "b"),
    )
    duration, component_id = _duration_input("sha256:" + "c" * 64)
    positive = _write(tmp_path / "positive.json", duration)
    return null_a, null_b, positive, component_id


def test_builds_deterministic_loader_shape_with_exact_provenance(tmp_path: Path) -> None:
    tool = _tool()
    null_a, null_b, positive, component_id = _inputs(tmp_path)

    result = tool.build_calibration(
        null_scan_paths=[null_b, null_a],
        positive_components=[(positive, component_id)],
        score_threshold=0.1,
        detection_probability=0.75,
        familywise_alpha=0.05,
    )
    reordered = tool.build_calibration(
        null_scan_paths=[null_a, null_b],
        positive_components=[(positive, component_id)],
        score_threshold=0.1,
        detection_probability=0.75,
        familywise_alpha=0.05,
    )

    assert result == reordered
    assert result["schema"] == "org.leo.research.raw-pilot-activity-score-calibration/v3"
    assert result["score_threshold"] == 0.1
    assert result["detection_probability"] == 0.75
    assert result["confidence"]["familywise_alpha"] == 0.05
    assert result["confidence"]["null_source_count"] == 2
    assert result["null"]["positive_group_count"] == 3
    assert result["null"]["group_count"] == 66
    rank0 = result["null"]["rank_buckets"][0]
    assert rank0["label"] == "rank0"
    assert rank0["null"]["positive_group_count"] == 3
    assert rank0["null"]["group_count"] == 66
    assert len(rank0["null"]["source_bounds"]) == 2
    null_upper = rank0["null"]["positive_intensity_upper_per_probe"]
    assert 0.0 < null_upper < 1.0
    signal_lower = rank0["signal"]["positive_mark_probability_lower"]
    assert 0.0 < signal_lower < 2.0 / 3.0
    assert result["signal"] == {
        "positive_group_count": 2,
        "group_count": 3,
    }
    assert result["accounting"] == {
        "null_input_file_count": 2,
        "signal_component_spec_count": 1,
        "null_raw_glrt64_row_count": 66,
        "null_deduplicated_glrt64_row_count": 66,
        "null_resolution_group_count": 66,
        "signal_raw_glrt64_row_count": 4,
        "signal_deduplicated_glrt64_row_count": 3,
        "signal_resolution_group_count": 3,
        "signal_unique_resolution_group_probe_count": 3,
    }
    assert result["sources"]["disjoint_pilot_scan_digests"] is True
    null_sources = result["sources"]["null"]
    assert {source["file_digest"] for source in null_sources} == {
        _digest(null_a),
        _digest(null_b),
    }
    assert {source["path"] for source in null_sources} == {
        str(null_a.resolve()),
        str(null_b.resolve()),
    }
    signal_source = result["sources"]["signal"][0]
    assert signal_source["file_digest"] == _digest(positive)
    assert signal_source["pilot_scan"]["file_digest"] == "sha256:" + "c" * 64
    assert signal_source["raw_glrt64_row_count"] == 4
    assert signal_source["deduplicated_glrt64_row_count"] == 3
    assert signal_source["duplicate_glrt64_row_count"] == 1
    assert signal_source["unique_resolution_group_probe_count"] == 3
    assert result["costs"]["missed_detection_cost"] == pytest.approx(-math.log(0.25))
    assert rank0["costs"]["positive"]["clutter_cost"] == pytest.approx(-math.log(null_upper))
    assert rank0["costs"]["positive"]["matched_base_cost"] == pytest.approx(
        -math.log(0.75) - math.log(signal_lower)
    )
    assert result["null"]["rank_buckets"][1]["costs"]["positive"]["match_supported"] is False
    assert any("exact-minus-control margin" in caveat for caveat in result["caveats"])
    json.dumps(result, sort_keys=True, allow_nan=False)


def test_zero_count_rank_intensity_and_worst_source_envelope_are_conservative(
    tmp_path: Path,
) -> None:
    tool = _tool()
    noisy = _write(
        tmp_path / "noisy.json",
        _null_scan([0.2, 0.1, *([0.0] * 31)], "a"),
    )
    clean = _write(
        tmp_path / "clean.json",
        _null_scan([0.0] * 33, "b"),
    )
    duration, component_id = _duration_input("sha256:" + "c" * 64)
    positive = _write(tmp_path / "positive.json", duration)

    one_source = tool.build_calibration(
        null_scan_paths=[noisy],
        positive_components=[(positive, component_id)],
        score_threshold=0.1,
        detection_probability=0.75,
        familywise_alpha=0.05,
    )
    two_sources = tool.build_calibration(
        null_scan_paths=[clean, noisy],
        positive_components=[(positive, component_id)],
        score_threshold=0.1,
        detection_probability=0.75,
        familywise_alpha=0.05,
    )

    one_buckets = one_source["null"]["rank_buckets"]
    assert one_buckets[1]["null"]["positive_intensity_upper_per_probe"] == pytest.approx(
        one_buckets[3]["null"]["positive_intensity_upper_per_probe"]
    )
    assert (
        two_sources["null"]["rank_buckets"][0]["null"]["positive_intensity_upper_per_probe"]
        >= one_buckets[0]["null"]["positive_intensity_upper_per_probe"]
    )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("summary", "summary-only"),
        ("candidate_truncation", "truncated duration-input candidate"),
        ("frame_truncation", "truncated duration-input frame"),
        ("capture_truncation", "truncated duration-input capture"),
    ],
)
def test_refuses_incomplete_positive_inputs(tmp_path: Path, field: str, message: str) -> None:
    tool = _tool()
    null_path = _write(tmp_path / "null.json", _null_scan([0.2], "a"))
    duration, component_id = _duration_input("sha256:" + "c" * 64)
    if field == "summary":
        duration["per_probe_rows_omitted"] = True
    elif field == "candidate_truncation":
        duration["scheduled_probes"][0]["truncated_candidate_count"] = 1
    elif field == "frame_truncation":
        duration["frame_evidence_inventory"]["alias_expanded_truncated_track_count"] = 1
    else:
        duration["capture"]["observed_sample_count"] = 999
    positive = _write(tmp_path / "positive.json", duration)

    with pytest.raises(ValueError, match=message):
        tool.build_calibration(
            null_scan_paths=[null_path],
            positive_components=[(positive, component_id)],
            score_threshold=0.1,
            detection_probability=0.75,
            familywise_alpha=0.05,
        )


def test_refuses_truncated_or_ambiguous_null_glrt64_rows(tmp_path: Path) -> None:
    tool = _tool()
    duration, component_id = _duration_input("sha256:" + "c" * 64)
    positive = _write(tmp_path / "positive.json", duration)
    truncated = _null_scan([0.2], "a")
    truncated["detections"][0]["truncated_candidate_count"] = 1
    truncated_path = _write(tmp_path / "truncated.json", truncated)
    ambiguous = _null_scan([0.2], "b")
    ambiguous["detections"][0]["candidates"][0]["scores"].append(
        {"method": "glrt64", "exact_score": 0.3, "control_score": 0.1, "margin": 0.2}
    )
    ambiguous_path = _write(tmp_path / "ambiguous.json", ambiguous)
    inconsistent = _null_scan([0.2], "c")
    inconsistent["detections"][0]["candidates"][0]["scores"][0]["margin"] = 0.19
    inconsistent_path = _write(tmp_path / "inconsistent.json", inconsistent)

    for path, message in (
        (truncated_path, "truncated null"),
        (ambiguous_path, "exactly one GLRT64"),
        (inconsistent_path, "inconsistent with exact minus control"),
    ):
        with pytest.raises(ValueError, match=message):
            tool.build_calibration(
                null_scan_paths=[path],
                positive_components=[(positive, component_id)],
                score_threshold=0.1,
                detection_probability=0.75,
                familywise_alpha=0.05,
            )


def test_refuses_conflicting_positive_duplicate_and_overlapping_sources(tmp_path: Path) -> None:
    tool = _tool()
    null_path = _write(tmp_path / "null.json", _null_scan([0.2], "a"))
    conflicting, component_id = _duration_input("sha256:" + "c" * 64)
    conflicting["branches"][1]["observations"][0]["glrt64_exact_score"] = 0.26
    conflicting["branches"][1]["observations"][0]["glrt64_margin"] = 0.21
    conflicting_path = _write(tmp_path / "conflicting.json", conflicting)
    with pytest.raises(ValueError, match="conflicting duplicate positive GLRT64 row"):
        tool.build_calibration(
            null_scan_paths=[null_path],
            positive_components=[(conflicting_path, component_id)],
            score_threshold=0.1,
            detection_probability=0.75,
            familywise_alpha=0.05,
        )

    multi_group, component_id = _duration_input("sha256:" + "d" * 64)
    second_group = multi_group["branches"][1]["observations"][1]
    second_group["probe_id"] = "probe-1"
    second_group["probe_sample_start"] = 100
    second_group["candidate_rank"] = 1
    second_group["source_tracking_cfo_hz"] = 5_000.0
    multi_group_path = _write(tmp_path / "multi-group.json", multi_group)
    with pytest.raises(ValueError, match="at most one resolution group per probe"):
        tool.build_calibration(
            null_scan_paths=[null_path],
            positive_components=[(multi_group_path, component_id)],
            score_threshold=0.1,
            detection_probability=0.75,
            familywise_alpha=0.05,
        )

    overlapping, component_id = _duration_input(_digest(null_path))
    overlapping_path = _write(tmp_path / "overlapping.json", overlapping)
    with pytest.raises(ValueError, match="overlapping calibration source pilot-scan digests"):
        tool.build_calibration(
            null_scan_paths=[null_path],
            positive_components=[(overlapping_path, component_id)],
            score_threshold=0.1,
            detection_probability=0.75,
            familywise_alpha=0.05,
        )


def test_refuses_duplicate_source_file_and_qnap_output(tmp_path: Path) -> None:
    tool = _tool()
    null_path = _write(tmp_path / "null.json", _null_scan([0.2], "a"))
    duration, component_id = _duration_input("sha256:" + "c" * 64)
    positive = _write(tmp_path / "positive.json", duration)

    with pytest.raises(ValueError, match="overlapping calibration source pilot-scan digests"):
        tool.build_calibration(
            null_scan_paths=[null_path, null_path],
            positive_components=[(positive, component_id)],
            score_threshold=0.1,
            detection_probability=0.75,
            familywise_alpha=0.05,
        )
    with pytest.raises(ValueError, match="/mnt/qnap01"):
        tool._output_path(Path("/mnt/qnap01/research/calibration.json"))
