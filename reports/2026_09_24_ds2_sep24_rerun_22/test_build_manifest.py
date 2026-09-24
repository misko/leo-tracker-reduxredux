# Test fixtures preserve the contract values on one line where that aids comparison.
# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds2_22_manifest", HERE / "build_manifest.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["ds2_22_manifest"] = MODULE
SPEC.loader.exec_module(MODULE)


def source_session(number: int) -> dict:
    session_id = f"scan-fw-source-{number:02d}"
    geometry: dict = {"eligibility": "unavailable", "reason": "no_explicit_capture_time_receiver_geometry"}
    if number < 3:
        session_id = sorted(MODULE.GEOMETRY_SESSION_IDS)[number]
        geometry = {
            "eligibility": "conditional_provisional_mapping",
            "capture_binding_digest": "sha256:capture",
            "fixture_digest": "sha256:fixture",
            "assignments": [{"receiver_id": 0}, {"receiver_id": 1}],
        }
    return {
        "session_id": session_id,
        "captured_at": f"2026-09-24T00:{number:02d}:00Z",
        "radio_id": "radio_a" if number < 3 else "radio_b",
        "sample_rate_hz": 2_500_000,
        "input_manifest_sha256": f"sha256:raw-{number}",
        "candidate_policy_digest": "sha256:policy",
        "tracking": {"tracking_product_digest": f"sha256:tracking-{number}", "candidate_policy_digest": "sha256:policy"},
        "receiver_geometry": geometry,
    }


def source() -> tuple[dict, dict, dict]:
    rows = [source_session(number) for number in range(20)]
    receipts = {
        row["session_id"]: {"session_id": row["session_id"], "state": "complete"}
        for row in rows
    }
    return (
        {"schema": "ds2-whole-corpus-manifest/v1", "manifest_sealed": True, "sessions": rows},
        {"receipts": {row["session_id"]: "sha256:receipt" for row in rows}},
        receipts,
    )


def addition(session_id: str, index: int) -> dict:
    raw_digest = f"sha256:additional-raw-{index}"
    raw = {
        "sha256": raw_digest,
        "manifest": {
            "session_id": session_id,
            "timing": {"qualified": True, "sample_rate_hz": 2_500_000, "first_sample_estimate_utc_ns": 1_790_212_000_000_000_000 + index},
            "receipt": {"radio_id": "radio_a", "source_span_attested": True, "terminal": {"state": "completed"}},
            "uncompressed_sha256": "sha256:iq",
            "uncompressed_bytes": 10,
            "total_sample_count": 5,
        },
    }
    product = {
        "document": {
            "session_id": session_id,
            "schema_version": 14,
            "analysis_id": "scanner-shared-tracking-v14",
            "input_manifest_sha256": raw_digest,
            "analysis_manifest_sha256": f"sha256:product-{index}",
            "tle_match_config_digest": "sha256:policy",
            "sample_rate_hz": 2_500_000,
            "trajectory_state": "complete",
            "tle_state": "complete",
            "tracklets": [],
            "tle_candidates": [],
            "artifacts": [],
        }
    }
    return MODULE.additional_input(session_id, raw, product)


def test_merge_rebuilds_a_coordinate_free_all22_manifest_and_keeps_only_three_bindings():
    source_manifest, index, receipts = source()
    additions = [addition(session_id, number) for number, session_id in enumerate(MODULE.ADDITIONAL_SESSION_IDS)]
    manifest, admission, merged_receipts = MODULE.assemble(
        source_manifest, index, receipts, additions,
        source_manifest_digest="sha256:source", source_receipt_index_digest="sha256:index",
    )
    assert manifest["counts"] == {
        "sessions": 22,
        "completed_tracking_products": 22,
        "cohorts": 2,
        "geometry_conditional_sessions": 3,
        "newly_admitted_sessions": 2,
    }
    assert manifest["geometry_policy"]["ordinary_models"] == "all 22 completed sessions"
    assert manifest["reference_coordinate_in_manifest"] is False
    assert "blind_priors" not in manifest
    assert manifest["geometry_policy"]["eligible_sessions"] == sorted(MODULE.GEOMETRY_SESSION_IDS)
    assert len(merged_receipts) == 22
    assert admission["new_session_admissions"][0]["geometry_admission"].startswith("not admitted")
    assert MODULE.coordinate_free(manifest)


def test_additional_product_requires_completed_tracking_and_raw_digest_binding():
    session_id = MODULE.ADDITIONAL_SESSION_IDS[0]
    raw = {"sha256": "sha256:raw", "manifest": {"session_id": session_id}}
    product = {"document": {"session_id": session_id, "input_manifest_sha256": "sha256:different"}}
    with pytest.raises(ValueError, match="input digest"):
        MODULE.additional_input(session_id, raw, product)
