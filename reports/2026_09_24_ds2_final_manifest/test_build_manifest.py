from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds2_final_manifest", HERE / "build_manifest.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["ds2_final_manifest"] = MODULE
SPEC.loader.exec_module(MODULE)


def inventory() -> dict:
    scans = []
    for number in range(20):
        scans.append(
            {
                "session_id": f"scan-fw-{number:016x}",
                "captured_at": f"2026-09-24T00:{number:02d}:00Z",
                "radio_id": "radio_pluto_19f2" if number < 3 else "radio_pluto_5d4d",
                "sample_rate_hz": 2_500_000,
                "input_manifest_sha256": f"sha256:input-{number}",
                "inclusion": {"raw_capture_eligible": True},
            }
        )
    return {"schema": "ds2-adaptive-inventory/v1", "scans": scans}


def plan() -> dict:
    actions = []
    for number in range(20):
        entry = {
            "session_id": f"scan-fw-{number:016x}",
            "receiver_geometry": {"status": "absent_from_capture_manifest"},
            "registry_geometry": {"status": "no_explicit_registry_match"},
        }
        if number < 3:
            entry["receiver_geometry"] = {
                "status": "explicit_capture_binding",
                "binding_digest": "sha256:binding",
                "fixture_part_id": "LT3D-001A",
                "fixture_digest": "sha256:fixture",
                "assignments": [
                    {"receiver_id": 0, "slot_id": "negative-x", "mapping_status": "provisional"},
                    {"receiver_id": 1, "slot_id": "positive-x", "mapping_status": "provisional"},
                ],
            }
            entry["registry_geometry"] = {
                "status": "explicit_registry_match",
                "station_geometry_digest": "sha256:station",
            }
        actions.append(entry)
    return {"schema": "ds2-frozen-backfill-plan/v1", "actions": actions}


def tracking(session_id: str, input_digest: str, state: str = "complete") -> dict:
    return {
        "session_id": session_id,
        "state": state,
        "phase": state,
        "product": {
            "schema_version": 14,
            "analysis_id": "scanner-shared-tracking-v14",
            "input_manifest_sha256": input_digest,
            "analysis_manifest_sha256": "sha256:product" if state == "complete" else None,
            "configuration_digest": "sha256:config",
            "tle_match_config_digest": "sha256:policy",
            "eligible_tle_snapshot": {"digest": "sha256:tle"},
            "tracklets": [],
            "tle_candidates": [],
            "review_count": 0,
            "artifacts": [],
            "observer_site": {"latitude_deg": 0.0},
        },
    }


def test_whole_corpus_manifest_has_one_development_group_per_cohort(tmp_path, monkeypatch):
    records = {
        row["session_id"]: tracking(row["session_id"], row["input_manifest_sha256"])
        for row in inventory()["scans"]
    }
    monkeypatch.setattr(MODULE, "fetch_tracking", lambda _endpoint, session_id: records[session_id])
    result = MODULE.build(
        inventory(), plan(), "unused", tmp_path, observed_utc="2026-09-24T16:00:00Z"
    )
    assert result["counts"]["sessions"] == 20
    assert result["whole_session_policy"].endswith("no train_validation_test_partition")
    assert "do not freeze" in result["association_policy"]["blind_inference_requirement"]
    assert len({row["session_id"] for row in result["sessions"]}) == 20
    assert [row["session_count"] for row in result["cohorts"]] == [3, 17]
    assert result["geometry_policy"]["eligible_sessions"] == [
        f"scan-fw-{number:016x}" for number in range(3)
    ]
    receipt = tmp_path / "tracking_receipts" / "scan-fw-0000000000000000.json"
    assert "observer_site" not in receipt.read_text()


def test_incomplete_tracking_prevents_seal(tmp_path, monkeypatch):
    rows = inventory()["scans"]
    records = {
        row["session_id"]: tracking(row["session_id"], row["input_manifest_sha256"]) for row in rows
    }
    records[rows[-1]["session_id"]] = tracking(
        rows[-1]["session_id"], rows[-1]["input_manifest_sha256"], state="pending"
    )
    monkeypatch.setattr(MODULE, "fetch_tracking", lambda _endpoint, session_id: records[session_id])
    with pytest.raises(RuntimeError, match="not complete"):
        MODULE.build(inventory(), plan(), "unused", tmp_path)
    assert not (tmp_path / "tracking_receipts").exists()


def test_capture_geometry_is_not_inferred_from_radio_identity():
    unavailable = MODULE.session_geometry(
        {
            "capture": {"status": "absent_from_capture_manifest"},
            "registry": {"status": "explicit_registry_match"},
        }
    )
    assert unavailable["eligibility"] == "unavailable"
