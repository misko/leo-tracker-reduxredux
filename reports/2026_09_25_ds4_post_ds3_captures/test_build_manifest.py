from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds4_build_manifest", HERE / "build_manifest.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(index: int) -> dict:
    return {
        "session_id": f"scan-fw-{index:016x}",
        "capture_start_utc": f"2026-09-25T00:{index:02d}:00Z",
        "admission_status": "included",
    }


def test_evaluation_units_are_whole_nonoverlapping_sessions() -> None:
    policy = {
        "schema": "ds4-freeze-policy/v1",
        "audit_observed_utc": "2026-09-25T01:00:00Z",
        "capture_start_lower_bound_utc": "2026-09-24T22:20:02.797011Z",
        "capture_start_upper_bound_utc": "2026-09-25T01:00:00Z",
        "source_root": "/read-only",
    }
    ds3 = {
        "captures": [
            {
                "session_id": "scan-fw-ds3",
                "capture_start_utc": "2026-09-24T22:20:02.797011Z",
                "admission_status": "included",
            }
        ]
    }
    manifest, units = MODULE.assemble(policy, ds3, [row(index) for index in range(19)])
    assert manifest["counts"] == {
        "discovered_in_interval": 19,
        "admitted": 19,
        "excluded": 0,
        "single_scan_units": 19,
        "complete_8_scan_units": 2,
        "sessions_in_complete_8_scan_units": 16,
        "8_scan_remainder_sessions": 3,
        "full_dataset_units": 1,
    }
    assert len(units["single_scans"]) == 19
    assert [item["session_count"] for item in units["groups_of_8"]] == [8, 8]
    grouped = [sid for item in units["groups_of_8"] for sid in item["session_ids"]]
    assert len(grouped) == len(set(grouped)) == 16
    assert units["groups_of_8_remainder"]["session_ids"] == [
        row(i)["session_id"] for i in range(16, 19)
    ]
    assert units["full_dataset"]["session_ids"] == [row(i)["session_id"] for i in range(19)]
    assert units["session_inventory_sha256"] == manifest["session_inventory_sha256"]


def test_excluded_capture_is_not_an_evaluation_unit() -> None:
    policy = {
        "schema": "ds4-freeze-policy/v1",
        "audit_observed_utc": "2026-09-25T01:00:00Z",
        "capture_start_lower_bound_utc": "2026-09-24T22:20:02.797011Z",
        "capture_start_upper_bound_utc": "2026-09-25T01:00:00Z",
        "source_root": "/read-only",
    }
    ds3 = {
        "captures": [
            {
                "session_id": "scan-fw-ds3",
                "capture_start_utc": "2026-09-24T22:20:02.797011Z",
                "admission_status": "included",
            }
        ]
    }
    excluded = row(9)
    excluded["admission_status"] = "excluded"
    manifest, units = MODULE.assemble(policy, ds3, [*map(row, range(9)), excluded])
    assert manifest["counts"]["admitted"] == 9
    assert manifest["counts"]["excluded"] == 1
    assert all(excluded["session_id"] not in item["session_ids"] for item in units["single_scans"])
