import hashlib
import json
from pathlib import Path
import importlib.util
import sys

import pytest


PATH = Path(__file__).with_name("select_confirmation.py")
SPEC = importlib.util.spec_from_file_location("confirmation_selection", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_selects_earliest_four_ready_after_development_without_outcomes():
    assert MODULE.METADATA_CUTOFF_UTC_NS == 1790486050012766163
    rows = [
        {"session_id": str(i), "capture_start_utc_ns": i, "pose_valid": True,
         "pose_error": None, "tracking_ready": i not in {12, 15}}
        for i in range(9, 18)
    ]
    selected, accounting = MODULE.select_earliest_ready(
        rows, {"9", "10"}, after_utc_ns=10, cutoff_utc_ns=17
    )
    assert [row["session_id"] for row in selected] == ["11", "13", "14", "16"]
    assert next(row for row in accounting if row["session_id"] == "12")[
        "exclusion_reasons"] == ["tracking_analysis_not_ready"]


def test_cutoff_disjointness_and_pose_failure_are_reported():
    rows = [
        {"session_id": "dev", "capture_start_utc_ns": 20, "pose_valid": True,
         "pose_error": None, "tracking_ready": True},
        {"session_id": "bad", "capture_start_utc_ns": 21, "pose_valid": False,
         "pose_error": "digest", "tracking_ready": True},
        {"session_id": "late", "capture_start_utc_ns": 99, "pose_valid": True,
         "pose_error": None, "tracking_ready": True},
    ] + [
        {"session_id": f"ok{i}", "capture_start_utc_ns": 30+i, "pose_valid": True,
         "pose_error": None, "tracking_ready": True} for i in range(4)
    ]
    _, accounting = MODULE.select_earliest_ready(rows, {"dev"}, 20, 40)
    reasons = {row["session_id"]: row["exclusion_reasons"] for row in accounting}
    assert "development_cohort" in reasons["dev"]
    assert "invalid_pose_binding" in reasons["bad"]
    assert "after_metadata_cutoff" in reasons["late"]


def test_insufficient_ready_fails_closed():
    row = {"session_id": "one", "capture_start_utc_ns": 2, "pose_valid": True,
           "pose_error": None, "tracking_ready": True}
    with pytest.raises(ValueError, match="only 1"):
        MODULE.select_earliest_ready([row], set(), 1, 3)


def test_pose_binding_and_authority_are_cryptographically_checked():
    authority = {"valid_from_utc_ns": 0, "valid_until_utc_ns": 100}
    pose = {"session_id": "s", "capture_start_earliest_utc_ns": 10,
            "capture_end_utc_ns": 20, "pose_authority": authority}
    pose["pose_authority_digest"] = MODULE.digest(MODULE.canonical(authority))
    pose["binding_digest"] = MODULE.digest(MODULE.canonical(pose))
    MODULE.validate_pose(pose)
    pose["capture_end_utc_ns"] = 30
    with pytest.raises(ValueError, match="binding"):
        MODULE.validate_pose(pose)
