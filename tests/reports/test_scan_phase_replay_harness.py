from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay"


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPORT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = _module("scan_phase_replay_common", "common.py")


def _readonly(value: np.ndarray) -> np.ndarray:
    value.setflags(write=False)
    return value


def test_visit_arrays_preserve_distinct_integer_axes_and_mask_semantics() -> None:
    n = common.VISIT_SAMPLES
    source = np.full((n, 2), int(common.SourceMask.RF_VALID), dtype=np.uint8)
    source[7, :] = int(common.SourceMask.KNOWN_NON_IQ)
    valid = (source & int(common.SourceMask.RF_VALID) != 0) & (
        source & common.INVALID_SOURCE_BITS == 0
    )
    coordinates = common.VisitCoordinates(3, 5, 2, "upper", 10**12, 10**12 + n, 7 * n)
    visit = common.ReplayVisitArrays(
        coordinates,
        _readonly(np.zeros((n, 2, 2), dtype="<i2")),
        _readonly(np.ascontiguousarray(valid)),
        _readonly(source),
        _readonly(np.arange(10**12, 10**12 + n, dtype=np.int64)),
        _readonly(np.arange(7 * n, 8 * n, dtype=np.int64)),
    )
    assert not visit.valid_mask[7].any()
    assert visit.device_counter[0] != visit.stored_sample_index[0]
    assert visit.complex64(0).dtype == np.complex64
    assert not visit.complex64(0).flags.writeable


def test_array_contract_rejects_writable_or_inconsistent_inputs() -> None:
    n = common.VISIT_SAMPLES
    coordinates = common.VisitCoordinates(0, 4, 1, "upper", 100, 100 + n, 0)
    with pytest.raises(ValueError, match="read-only"):
        common.ReplayVisitArrays(
            coordinates,
            np.zeros((n, 2, 2), dtype="<i2"),
            _readonly(np.ones((n, 2), dtype=np.bool_)),
            _readonly(np.ones((n, 2), dtype=np.uint8)),
            _readonly(np.arange(100, 100 + n, dtype=np.int64)),
            _readonly(np.arange(n, dtype=np.int64)),
        )


def test_counter_conversion_subtracts_integer_origin_before_float() -> None:
    origin = 9_007_199_254_740_992
    counters = np.array([origin, origin + 1, origin + 10], dtype=np.uint64)
    seconds = common.seconds_from_counter(counters, integer_origin=origin)
    np.testing.assert_array_equal(seconds, [0.0, 1e-7, 1e-6])


def test_expanded_support_leakage_check_is_boundary_aware() -> None:
    assert common.support_is_disjoint([10, 20], [15, 30], expansion_samples=2)
    assert not common.support_is_disjoint([10, 20], [15, 30], expansion_samples=3)
    assert not common.support_is_disjoint([10], [10], expansion_samples=0)


def test_selection_is_complete_stratified_and_locked() -> None:
    document = json.loads((REPORT / "selection.json").read_text())
    assert document["counts"] == {"development": 32, "evaluation": 96, "selected": 128}
    assert document["development_start4_visit_indices"] == [177, 250, 86, 106]
    assert document["smoke8_visit_indices"] == [177, 194, 250, 2, 86, 161, 106, 139]
    rows = document["visits"]
    for target in (4, 5, 6, 7):
        for bin_index in range(8):
            group = [r for r in rows if r["target_index"] == target and r["time_bin"] == bin_index]
            assert len(group) == 4
            assert all(
                r["split"] == ("development" if bin_index < 2 else "evaluation") for r in group
            )
    seed = document["selection_policy"]["seed"]
    for row in rows:
        identity = (
            f"{seed}:{row['target_index']}:{row['time_bin']}:"
            f"{row['visit_index']}:{row['valid_start_counter']}"
        )
        assert row["rank_sha256"] == "sha256:" + hashlib.sha256(identity.encode()).hexdigest()
        first, stop = document["selection_policy"]["device_counter_range"]
        span = stop - first
        lower = first + span * row["time_bin"] // 8
        upper = first + span * (row["time_bin"] + 1) // 8
        assert lower <= row["valid_start_counter"] < row["valid_end_counter_exclusive"] <= upper


def test_registry_accounts_for_all_30_rows_and_schema_documents_parse() -> None:
    registry = json.loads((REPORT / "method-registry.json").read_text())
    assert registry["counts"] == {"ledger_rows": 30, "required": 30}
    assert [m["ledger_row"] for m in registry["methods"]] == list(range(1, 31))
    assert len({m["method_id"] for m in registry["methods"]}) == 30
    assert all(m["historical_report_refs"] for m in registry["methods"])
    for filename in ("result-schema.json", "observation-schema.json"):
        schema = json.loads((REPORT / filename).read_text())
        assert schema["$schema"].endswith("2020-12/schema")
