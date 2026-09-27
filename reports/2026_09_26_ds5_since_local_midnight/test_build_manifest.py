from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds5_build_manifest", HERE / "build_manifest.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def policy() -> dict:
    return {
        "schema": "ds5-freeze-policy/v1",
        "audit_observed_utc": "2026-09-26T14:00:00Z",
        "capture_start_lower_bound_utc": "2026-09-26T07:00:00Z",
        "capture_start_upper_bound_utc": "2026-09-26T14:00:00Z",
        "source_root": "/read-only",
        "reference_coordinate_present": False,
        "window_basis": {"timezone": "America/Los_Angeles"},
    }


def row(index: int, rate: int = 2_500_000, included: bool = True) -> dict:
    return {
        "session_id": f"scan-fw-{index:016x}",
        "capture_start_utc": f"2026-09-26T07:{index:02d}:00Z",
        "sample_rate_hz": rate,
        "active_dwell_seconds": 260.0 + index / 10,
        "valid_duty_fraction": 0.88 + index / 10_000,
        "median_visit_dwell_ms": 120.0,
        "admission_status": "included" if included else "excluded",
    }


def walk_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [key for item in value.values() for key in walk_keys(item)]
    if isinstance(value, list):
        return [key for item in value for key in walk_keys(item)]
    return []


def test_units_preserve_whole_chronological_sessions_and_remainder() -> None:
    rates = [2_500_000, 5_000_000, 7_500_000, 10_000_000]
    rows = [row(index, rates[index % 4]) for index in range(19)]
    manifest, units = MODULE.assemble(policy(), rows)
    assert manifest["counts"] == {
        "discovered_in_interval": 19,
        "admitted": 19,
        "excluded": 0,
        "single_scan_units": 19,
        "complete_8_scan_units": 2,
        "sessions_in_complete_8_scan_units": 16,
        "8_scan_remainder_sessions": 3,
        "sample_rate_strata": 4,
        "active_dwell_time_strata": 3,
        "full_dataset_units": 1,
    }
    expected = [item["session_id"] for item in rows]
    assert units["full_dataset"]["session_ids"] == expected
    grouped = [sid for unit in units["groups_of_8"] for sid in unit["session_ids"]]
    assert grouped == expected[:16]
    assert len(grouped) == len(set(grouped))
    assert units["groups_of_8_remainder"]["session_ids"] == expected[16:]
    assert units["groups_of_8_remainder"]["eligible_as_8_scan_unit"] is False


def test_rate_strata_partition_admitted_inventory_without_reordering_groups() -> None:
    rates = [2_500_000, 5_000_000, 2_500_000, 10_000_000] * 2
    rows = [row(index, rate) for index, rate in enumerate(rates)]
    _, units = MODULE.assemble(policy(), rows)
    assert units["groups_of_8"][0]["session_ids"] == [item["session_id"] for item in rows]
    assert units["groups_of_8"][0]["sample_rate_composition"] == {
        "2500000": 4,
        "5000000": 2,
        "10000000": 2,
    }
    flattened: list[str] = []
    for rate, stratum in units["sample_rate_strata"].items():
        ids = stratum["ordered_single_session_ids"]
        assert stratum["session_count"] == len(ids)
        assert stratum["subset_unit"]["session_ids"] == ids
        assert stratum["subset_unit"]["sample_rate_composition"] == {rate: len(ids)}
        flattened.extend(ids)
    assert sorted(flattened) == sorted(item["session_id"] for item in rows)
    assert len(flattened) == len(set(flattened))


def test_excluded_capture_is_absent_from_every_evaluation_membership() -> None:
    rows = [row(index) for index in range(9)] + [row(9, included=False)]
    manifest, units = MODULE.assemble(policy(), rows)
    excluded = rows[-1]["session_id"]
    encoded = json.dumps(units)
    assert manifest["counts"]["admitted"] == 9
    assert manifest["counts"]["excluded"] == 1
    assert excluded not in encoded


def test_active_time_strata_partition_inventory_and_cross_with_rate() -> None:
    rates = [2_500_000, 5_000_000, 7_500_000, 10_000_000]
    rows = [row(index, rates[index % 4]) for index in range(12)]
    _, units = MODULE.assemble(policy(), rows)
    strata = units["active_dwell_time_strata"]
    assert {name: value["session_count"] for name, value in strata.items()} == {
        "low": 4,
        "middle": 4,
        "high": 4,
    }
    flattened = [sid for value in strata.values() for sid in value["ordered_session_ids"]]
    assert len(flattened) == len(set(flattened)) == 12
    cross_count = sum(
        cell["session_count"]
        for rate in units["sample_rate_active_dwell_cross_strata"].values()
        for cell in rate.values()
    )
    assert cross_count == 12
    assert units["full_dataset"]["active_dwell_support"]["total_seconds"] == sum(
        item["active_dwell_seconds"] for item in rows
    )


def test_inference_contract_contains_no_reference_or_truth_coordinate() -> None:
    manifest, units = MODULE.assemble(policy(), [row(index) for index in range(8)])
    for value in (manifest, units):
        keys = {key.lower() for key in walk_keys(value)}
        assert "latitude" not in keys
        assert "longitude" not in keys
        assert "ground_truth" not in keys
        assert value["reference_coordinate_present"] is False


def test_published_seals_and_inventory_bindings_are_consistent() -> None:
    manifest_path = HERE / "manifest.json"
    units_path = HERE / "evaluation-units.json"
    assert MODULE.verify_seal(HERE / "freeze-policy.json").startswith("sha256:")
    assert MODULE.verify_seal(manifest_path).startswith("sha256:")
    assert MODULE.verify_seal(units_path).startswith("sha256:")
    manifest = MODULE.load(manifest_path)
    units = MODULE.load(units_path)
    assert manifest["session_inventory_sha256"] == units["session_inventory_sha256"]
    assert units["admission_manifest"]["sha256"] == MODULE.verify_seal(manifest_path)
    assert units["full_dataset"]["session_ids"] == [
        item["session_id"]
        for item in manifest["captures"]
        if item["admission_status"] == "included"
    ]
