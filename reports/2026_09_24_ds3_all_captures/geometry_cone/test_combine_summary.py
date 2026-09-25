from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds3_geometry_summary", HERE / "combine_summary.py")
assert SPEC is not None and SPEC.loader is not None
SUMMARY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUMMARY
SPEC.loader.exec_module(SUMMARY)

SESSIONS = [f"scan-fw-{index}" for index in range(5)]
PLAN_DIGEST = "sha256:" + "1" * 64


def scenario(full_fov: int, loss: float) -> dict[str, Any]:
    return {
        "latitude_deg": 38.0 + loss,
        "longitude_deg": -121.0,
        "xy_km": [1.0, 2.0],
        "training_capped_loss": loss,
        "held_capped_loss": loss + 0.01,
        "supported_tracks": 9,
        "unsupported_tracks": 1,
        "supported_occupied_second_fraction": 0.9,
        "changed_candidate_id_count": 2,
        "full_fov_deg": full_fov,
        "mapping": [0, 1],
        "orientation_index": 3,
    }


def fixed_scenario(full_fov: int, loss: float) -> dict[str, Any]:
    row = scenario(full_fov, loss)
    for key in ("latitude_deg", "longitude_deg", "xy_km"):
        row.pop(key)
    return row


def plan() -> dict[str, Any]:
    return {
        "schema": SUMMARY.EXPECTED_PLAN_SCHEMA,
        "reference_used": False,
        "phase_used": False,
        "eligible_session_ids": SESSIONS,
        "models": [{"model_id": model_id} for model_id in SUMMARY.EXPECTED_MODEL_IDS],
    }


def cone(mode: str) -> dict[str, Any]:
    model_ids = (
        ["lt3d_geometry_only", "lt3d_learned_zenith_cone"]
        if mode == "learned15"
        else ["lt3d_fixed_up_cone"]
    )
    return {
        "schema": SUMMARY.EXPECTED_INFERENCE_SCHEMA,
        "complete": True,
        "reference_used_for_inference": False,
        "held_used_for_selection": False,
        "orientation_mode": mode,
        "top10_model_ids": model_ids,
        "ds3_bindings": {"geometry_plan": PLAN_DIGEST},
        "results": [
            {
                "label": "joint-five-geometry-captures",
                "session_ids": SESSIONS,
                "baseline": {
                    "latitude_deg": 38.1,
                    "longitude_deg": -121.2,
                    "xy_km": [3.0, 4.0],
                    "training_capped_loss": 0.2,
                    "converged": True,
                    "attempt_count": 5,
                },
                "staged_full_fov": {"track_count": 10},
                "local_fitted_cone": {
                    "winners": {"20": scenario(20, 0.3), "40": scenario(40, 0.1)}
                },
                "fixed_hard_half_angle": {
                    "10": fixed_scenario(20, 0.4),
                    "15": fixed_scenario(30, 0.3),
                    "20": fixed_scenario(40, 0.2),
                    "30": fixed_scenario(60, 0.1),
                },
            }
        ],
    }


def global_time(tau: float = 0.0) -> dict[str, Any]:
    return {
        "schema": SUMMARY.EXPECTED_GLOBAL_SCHEMA,
        "complete": True,
        "reference_coordinate_present": False,
        "reference_used_for_fit": False,
        "truth_used_for_fit": False,
        "method": "shared_global_tau",
        "session_ids": SESSIONS,
        "fitted_parameters": {"timing": {"global_tau_s": tau}},
        "estimated_position": {"latitude_deg": 38.2, "longitude_deg": -121.3},
        "rf_objective": {
            "selection_value": 0.15,
            "full_observation_capped_loss": 0.15,
        },
        "qualified_track_count": 10,
        "full_observation_count": 100,
        "occupied_second_denominator": 80,
    }


def provenance() -> dict[str, dict[str, str]]:
    return {
        name: {
            "path": f"/{name}.json",
            "sha256": "sha256:" + digit * 64,
            "seal_path": f"/{name}.json.sha256",
            "seal_value": "sha256:" + digit * 64,
        }
        for name, digit in (
            ("geometry_plan", "1"),
            ("learned15_inference", "2"),
            ("fixed_up_inference", "3"),
            ("global_time_control", "4"),
        )
    }


def test_combines_one_qualified_row_per_exact_plan_model() -> None:
    document = SUMMARY.combine(
        plan(), cone("learned15"), cone("fixed-up"), global_time(), provenance()
    )
    assert document["model_ids"] == list(SUMMARY.EXPECTED_MODEL_IDS)
    assert [row["model_id"] for row in document["models"]] == list(
        SUMMARY.EXPECTED_MODEL_IDS
    )
    assert {row["qualification"] for row in document["models"]} == {"qualified"}
    fixed = document["models"][1]["joint_five"]
    learned = document["models"][2]["joint_five"]
    reused = document["models"][3]["joint_five"]
    assert fixed["cone"]["full_fov_deg"] == 60.0
    assert fixed["position"]["latitude_deg"] == 38.1
    assert learned["cone"]["full_fov_deg"] == 40.0
    assert reused["position"] == learned["position"]
    assert reused["time_control"]["global_tau_s"] == 0.0
    assert reused["reuse"]["required_seals"] == [
        provenance()["learned15_inference"]["sha256"],
        provenance()["global_time_control"]["sha256"],
    ]
    assert document["reference_used_for_qualification"] is False


def test_nonzero_tau_fails_instead_of_reusing_learned_cone() -> None:
    with pytest.raises(ValueError, match="exactly equal to 0.0"):
        SUMMARY.combine(
            plan(), cone("learned15"), cone("fixed-up"), global_time(1e-12), provenance()
        )


def test_wrong_or_reordered_model_set_fails() -> None:
    changed = plan()
    changed["models"] = list(reversed(changed["models"]))
    with pytest.raises(ValueError, match="model IDs/order"):
        SUMMARY.combine(
            changed, cone("learned15"), cone("fixed-up"), global_time(), provenance()
        )


def test_reference_flag_must_be_explicitly_false() -> None:
    changed = cone("learned15")
    changed["reference_used_for_inference"] = None
    with pytest.raises(ValueError, match="reference_used_for_inference=false"):
        SUMMARY.combine(plan(), changed, cone("fixed-up"), global_time(), provenance())


def test_artifact_seal_is_verified(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps({"ok": True}) + "\n")
    path.with_suffix(".json.sha256").write_text("0" * 64 + "\n")
    with pytest.raises(ValueError, match="artifact seal mismatch"):
        SUMMARY.verified_artifact(path)


def test_sealed_output_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    SUMMARY.write_sealed(path, {"schema": "test"})
    assert path.with_suffix(".json.sha256").exists()
    with pytest.raises(FileExistsError, match="refusing to replace"):
        SUMMARY.write_sealed(path, {"schema": "test"})
