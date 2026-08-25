from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from leo.analysis.research.causal_cfo_acceleration import track_causal_cfo_acceleration
from leo.analysis.research.doppler_dataset_policy import (
    load_doppler_dataset_policy,
    verify_policy_inventory,
)
from tools import benchmark_causal_cfo_acceleration_development as tool

ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "config/analysis/causal-cfo-acceleration-development-v1.json"
OUTPUT_ROOT = ROOT / "reports/figures/2026_08_25_causal_cfo_acceleration_development"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _config() -> dict[str, object]:
    value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _evidence() -> dict[str, object]:
    value = json.loads((OUTPUT_ROOT / "evidence.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_protocol_is_the_exact_rate_development_partition() -> None:
    config = _config()
    policy_config = config["dataset_policy"]
    assert isinstance(policy_config, dict)
    policy_path = ROOT / str(policy_config["path"])
    assert _sha256(policy_path) == policy_config["sha256"]
    policy = load_doppler_dataset_policy(policy_path)
    verify_policy_inventory(policy, ROOT)

    expected_ids = tuple(policy_config["expected_capture_ids"])
    assert expected_ids == policy.role("rate_development").capture_ids
    assert not set(expected_ids) & set(policy.role("holdout_foundation").capture_ids)
    sources = config["serialized_sources"]
    unavailable = config["non_evaluable_sources"]
    assert isinstance(sources, list)
    assert isinstance(unavailable, list)
    serialized_ids = {
        session_id for source in sources for session_id in source["capture_labels"].values()
    }
    unavailable_ids = {item["session_id"] for item in unavailable}
    assert len(serialized_ids) == 10
    assert len(unavailable_ids) == 6
    assert serialized_ids | unavailable_ids == set(expected_ids)
    assert not serialized_ids & unavailable_ids
    for source in sources:
        assert (
            _sha256(ROOT / source["artifact_manifest_path"]) == source["artifact_manifest_sha256"]
        )
        assert _sha256(ROOT / source["payload_path"]) == source["payload_sha256"]


def test_evidence_retains_every_capture_and_source_failure() -> None:
    evidence = _evidence()
    assert evidence["schema"] == tool.SCHEMA
    assert evidence["protocol"]["sha256"] == _sha256(CONFIG_PATH)
    assert evidence["policy"]["holdout_foundation_consumed"] is False
    dispositions = evidence["capture_dispositions"]
    assert len(dispositions) == 16
    assert Counter(item["status"] for item in dispositions) == {
        "evaluable": 8,
        "non_evaluable": 8,
    }
    assert len(evidence["tile_failure_ledger"]) == 5
    assert evidence["scope"]["frozen_source_failure_count"] == 5
    gate = evidence["likelihood_gate"]
    assert gate["real_data_status_at_freeze"] == "unavailable"
    assert gate["real_data_invocation_count"] is None
    assert gate["unit_test_only"] is True
    assert evidence["uncertainty"] == {
        "covariance_claimed": False,
        "coverage_68_95_reported": False,
        "nis_reported": False,
        "reason": "robust local-polynomial covariance was not calibrated or claimed",
    }


def test_forecast_rows_are_identical_mask_and_strictly_future() -> None:
    with (OUTPUT_ROOT / "forecast-rows.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            row["session_id"],
            row["locklet_id"],
            row["continuity_segment"],
            row["target_frame_start_sample"],
            row["requested_horizon_ms"],
        )
        groups[key].append(row)
        assert float(row["actual_horizon_ms"]) + 1e-9 >= float(row["requested_horizon_ms"])
        assert int(row["cutoff_frame_start_sample"]) < int(row["target_frame_start_sample"])
        actual_s = float(row["actual_horizon_ms"]) / 1000.0
        expected = (
            float(row["cutoff_cfo_hz"])
            + float(row["cutoff_rate_hz_s"]) * actual_s
            + 0.5 * float(row["cutoff_acceleration_hz_s2"]) * actual_s**2
        )
        assert float(row["predicted_odd_cfo_hz"]) == pytest.approx(expected, abs=1e-5)
    assert len(rows) == 7_096
    assert all(len(values) == 4 for values in groups.values())
    for values in groups.values():
        assert {row["method"] for row in values} == set(tool.METHODS)
        assert len({row["cutoff_frame_start_sample"] for row in values}) == 1
        assert len({row["stratum"] for row in values}) == 1
        assert len({row["measured_odd_cfo_hz"] for row in values}) == 1


def test_equal_capture_aggregation_and_verdict_are_reproducible() -> None:
    evidence = _evidence()
    by_capture = evidence["forecast_metrics_by_capture"]
    aggregates = evidence["forecast_metrics_equal_capture"]
    for aggregate in aggregates:
        cells = [
            row
            for row in by_capture
            if row["method"] == aggregate["method"]
            and row["requested_horizon_ms"] == aggregate["requested_horizon_ms"]
        ]
        recomputed = math.sqrt(
            sum(float(row["future_odd_cfo_rms_hz"]) ** 2 for row in cells) / len(cells)
        )
        assert aggregate["equal_capture_future_odd_cfo_rms_hz"] == pytest.approx(
            recomputed, abs=1e-7
        )
    verdict = evidence["development_verdict"]
    assert verdict["status"] == "inconclusive"
    assert verdict["supporting_capture_count_by_horizon"] == {
        "125.0": 3,
        "500.0": 2,
        "1000.0": 2,
    }
    assert verdict["aggregate_candidate_to_fixed_500_rms_ratio"] == pytest.approx(
        {
            "125.0": 1.0543136218,
            "500.0": 2.67447051658,
            "1000.0": 4.63624463764,
        }
    )


def test_odd_qin_perturbation_changes_responses_but_not_mask_or_state() -> None:
    rows = []
    for index in range(900):
        time_s = index / 750.0
        even_hz = 50_000.0 - 3_500.0 * time_s + 100.0 * time_s**2
        rows.append(
            tool.FrameRow(
                capture_label="X1",
                session_id="cap-20260825T000000-000000000000",
                locklet_id="X1",
                frame_ordinal=index,
                frame_start_sample=index * 3333,
                reference_time_s=time_s,
                continuity_safe=True,
                training_supported=True,
                even_cfo_hz=even_hz,
                odd_cfo_hz=even_hz + 10.0,
            )
        )
    first_locklet = tool.Locklet("X1", rows[0].session_id, "X1", "synthetic", tuple(rows))
    changed_locklet = replace(
        first_locklet,
        rows=tuple(
            replace(row, odd_cfo_hz=row.odd_cfo_hz + (1e6 if index % 2 else -1e6))
            for index, row in enumerate(rows)
        ),
    )
    settings = tool._config_from_protocol(_config())
    points, segments = tool._training_points(
        first_locklet,
        measurement_sigma_hz=50.0,
        maximum_gap_s=settings.maximum_supported_point_gap_s,
    )
    changed_points, changed_segments = tool._training_points(
        changed_locklet,
        measurement_sigma_hz=50.0,
        maximum_gap_s=settings.maximum_supported_point_gap_s,
    )
    assert changed_points == points
    assert changed_segments == segments
    track = track_causal_cfo_acceleration(points, config=settings)
    changed_track = track_causal_cfo_acceleration(changed_points, config=settings)
    assert changed_track == track
    first, _ = tool._forecast_rows_for_locklet(
        first_locklet,
        track.estimates,
        segments,
        horizons_s=(0.125, 0.500, 1.000),
        target_stride_frames=15,
        sample_rate_hz=2_500_000,
    )
    changed, _ = tool._forecast_rows_for_locklet(
        changed_locklet,
        changed_track.estimates,
        changed_segments,
        horizons_s=(0.125, 0.500, 1.000),
        target_stride_frames=15,
        sample_rate_hz=2_500_000,
    )
    identity_fields = (
        "method",
        "target_frame_start_sample",
        "cutoff_frame_start_sample",
        "requested_horizon_ms",
        "actual_horizon_ms",
        "stratum",
        "candidate_mode",
    )
    assert [tuple(row[field] for field in identity_fields) for row in changed] == [
        tuple(row[field] for field in identity_fields) for row in first
    ]
    assert [row["predicted_odd_cfo_hz"] for row in changed] == [
        row["predicted_odd_cfo_hz"] for row in first
    ]
    assert [row["prediction_error_hz"] for row in changed] != [
        row["prediction_error_hz"] for row in first
    ]


def test_artifact_manifest_hashes_every_persisted_product() -> None:
    manifest = json.loads((OUTPUT_ROOT / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["protocol_sha256"] == _sha256(CONFIG_PATH)
    assert set(manifest["artifacts"]) == {
        "capture-dispositions.csv",
        "evidence.json",
        "forecast-rms.png",
        "forecast-rows.csv",
        "rate-acceleration-stability.png",
        "runtime-rows.csv",
        "state-rows.csv",
        "tile-dispositions.csv",
        "yield-and-mode.png",
    }
    for artifact in manifest["artifacts"].values():
        path = OUTPUT_ROOT / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert _sha256(path) == artifact["sha256"]
