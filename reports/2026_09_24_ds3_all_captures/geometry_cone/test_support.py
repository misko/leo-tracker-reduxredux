from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds3_geometry_cone_support", HERE / "support.py")
assert SPEC is not None and SPEC.loader is not None
SUPPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUPPORT
SPEC.loader.exec_module(SUPPORT)


def capture(session_id: str, *, radio_id: str = "radio_pluto_19f2") -> dict[str, Any]:
    return {
        "session_id": session_id,
        "capture_start_utc": "2026-09-24T01:08:02Z",
        "admission_status": "included",
        "radio_id": radio_id,
        "qualified_utc_timing": True,
        "recording_manifest_path": f"/read-only/{session_id}/manifest.json",
    }


def envelope(session_id: str, *, provisional: bool = True) -> dict[str, Any]:
    status = "provisional" if provisional else "confirmed"
    return {
        "manifest": {
            "session_id": session_id,
            "receiver_geometry": {
                "binding_digest": SUPPORT.BINDING_DIGEST,
                "station_geometry_digest": SUPPORT.STATION_GEOMETRY_DIGEST,
                "valid_from_utc_ns": 1_789_929_742_956_192_499,
                "valid_until_utc_ns": 9_223_372_036_854_775_807,
                "fixture": {
                    "fixture_part_id": SUPPORT.FIXTURE_PART_ID,
                    "fixture_digest": SUPPORT.FIXTURE_DIGEST,
                    "slots": [
                        {
                            "slot_id": "negative-x",
                            "mount_axis_unit": {"x": -0.17, "y": 0, "z": 0.98},
                            "rf_boresight_unit": None,
                            "rf_phase_center_position_m": None,
                        },
                        {
                            "slot_id": "positive-x",
                            "mount_axis_unit": {"x": 0.17, "y": 0, "z": 0.98},
                            "rf_boresight_unit": None,
                            "rf_phase_center_position_m": None,
                        },
                    ],
                },
                "radio": {
                    "fixture_part_id": SUPPORT.FIXTURE_PART_ID,
                    "fixture_digest": SUPPORT.FIXTURE_DIGEST,
                    "assignments": [
                        {
                            "receiver_id": 0,
                            "slot_id": "negative-x",
                            "mapping_status": status,
                        },
                        {
                            "receiver_id": 1,
                            "slot_id": "positive-x",
                            "mapping_status": status,
                        },
                    ],
                },
            },
        }
    }


def test_provisional_binding_is_eligible_only_with_both_mapping_hypotheses() -> None:
    result = SUPPORT.evaluate_capture(capture("scan-fw-bound"), envelope("scan-fw-bound"))
    assert result["status"] == "eligible"
    assert result["mapping_treatment"] == "symmetric_two_mapping_marginalization"
    assert result["mapping_hypotheses"] == [
        {"0": "negative-x", "1": "positive-x"},
        {"0": "positive-x", "1": "negative-x"},
    ]
    assert result["direction_source"] == "fixture_nominal_mount_axis_proxy"
    assert result["rf_phase_center_measured"] is False


def test_radio_identity_does_not_supply_missing_capture_binding() -> None:
    result = SUPPORT.evaluate_capture(
        capture("scan-fw-unbound", radio_id="radio_pluto_19f2"),
        {"manifest": {"session_id": "scan-fw-unbound"}},
    )
    assert result == {
        "session_id": "scan-fw-unbound",
        "status": "excluded",
        "reason": "capture_time_geometry_absent",
    }


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda item: item.update(capture_start_utc="2020-01-01T00:00:00Z"),
         "capture_outside_geometry_validity_interval"),
        (lambda item: item.update(admission_status="excluded"), "capture_not_admitted_to_ds3"),
    ],
)
def test_capture_level_failure_rules(mutation: Any, reason: str) -> None:
    row = capture("scan-fw-gated")
    mutation(row)
    assert SUPPORT.evaluate_capture(row, envelope("scan-fw-gated"))["reason"] == reason


def test_plan_exposes_closed_models_and_never_phase() -> None:
    rows = [capture("scan-fw-bound"), capture("scan-fw-same-radio-unbound")]
    manifest = {
        "schema": "ds3-all-captures-admission/v1",
        "capture_cutoff_utc": "2026-09-24T22:20:02.797011Z",
        "captures": rows,
    }
    documents = {
        "scan-fw-bound": envelope("scan-fw-bound"),
        "scan-fw-same-radio-unbound": {
            "manifest": {"session_id": "scan-fw-same-radio-unbound"}
        },
    }
    plan = SUPPORT.build_plan(manifest, lambda row: documents[row["session_id"]])
    assert plan["eligible_session_ids"] == ["scan-fw-bound"]
    assert plan["counts"] == {
        "captures_evaluated": 2,
        "geometry_eligible": 1,
        "geometry_excluded": 1,
    }
    assert [model["model_id"] for model in plan["models"]] == [
        "lt3d_geometry_only",
        "lt3d_fixed_up_cone",
        "lt3d_learned_zenith_cone",
        "global_time_plus_lt3d_cone",
    ]
    fixed = plan["models"][1]["fit"]
    assert fixed["fixed_half_angle_deg"] == [10, 15, 20, 30]
    assert fixed["equivalent_full_fov_deg"] == [20, 30, 40, 60]
    assert plan["phase_used"] is False
    assert all(
        "relative_receiver_phase" in model["prohibited_inputs"] for model in plan["models"]
    )


def test_unexpected_ds3_schema_is_rejected() -> None:
    with pytest.raises(ValueError, match="unexpected DS3 admission schema"):
        SUPPORT.build_plan({"schema": "other", "captures": []}, lambda _: {})
