"""Focused tests for the DS2 descriptive-quality report builder."""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds2_quality", HERE / "build_quality_report.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_distribution_uses_explicit_empty_and_median_conventions() -> None:
    assert MODULE.distribution([])["median"] is None
    assert MODULE.distribution([1.0, 3.0, 5.0])["median"] == 3.0
    assert MODULE.percentile([1.0, 5.0], 0.25) == 2.0


def test_control_outcome_marks_positive_delta_as_nominal_advantage() -> None:
    outcome = MODULE.control_outcome(
        {
            "nominal_heldout_negative_log_score": 10.0,
            "radio_null_heldout_negative_log_score": 13.0,
            "wrong_time_minus_500_heldout_negative_log_score": 15.0,
            "wrong_time_plus_500_heldout_negative_log_score": 12.0,
        }
    )
    assert outcome["radio_null_delta"] == 3.0
    assert outcome["nominal_beats_radio_null"] is True
    assert outcome["nominal_beats_both_wrong_times"] is True


def test_sanitized_product_omits_site_and_position_diagnostic() -> None:
    product = {
        "schema_version": 14,
        "session_id": "scan-fw-example",
        "observer_site": {"latitude_deg": 1.0},
        "position_diagnostic": {"candidate_latitude_deg": 2.0},
        "tracklets": [],
        "tle_candidates": [],
        "track_reviews": [],
    }
    result = MODULE.sanitized_product(product)
    assert "observer_site" not in result
    assert "position_diagnostic" not in result
    assert result["session_id"] == "scan-fw-example"


def test_build_rows_binds_product_to_frozen_capture_manifest() -> None:
    manifest = {
        "session_id": "scan-fw-example",
        "radio_id": "radio_a",
        "sample_rate_hz": 2_500_000,
        "input_manifest_sha256": "sha256:input",
        "retained_visits": 10,
        "source_span_seconds": 300.0,
    }
    product = {
        "input_manifest_sha256": "sha256:input",
        "tracklets": [
            {
                "tracklet_id": "track",
                "start_utc_ns": 1_000_000_000,
                "end_utc_ns": 4_000_000_000,
                "observation_count": 4,
                "residual_rms_hz": 12.5,
            }
        ],
        "track_reviews": [],
        "tle_candidates": [],
    }
    sessions, tracklets, reviews, candidates = MODULE.build_rows(
        [manifest], {"scan-fw-example": product}
    )
    assert len(sessions) == 1
    assert tracklets[0]["span_seconds"] == 3.0
    assert reviews == []
    assert candidates == []
