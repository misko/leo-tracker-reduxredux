import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "transfer_prepare", Path(__file__).with_name("prepare.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_chronological_selection_ignores_outcome_fields():
    rows = [
        {
            "session_id": name,
            "capture_start_utc_ns": start,
            "manifest_sha256": name,
            "sample_rate_hz": 1,
            "error_m": error,
        }
        for name, start, error in [("z", 2, 0), ("b", 1, 100), ("a", 1, 9999)]
    ]
    result = module.select({"dataset_id": "DS8", "captures": rows}, 2)
    assert [r["session_id"] for r in result] == ["a", "b"]
    assert not any("error_m" in r for r in result)
    assert result[0]["unit_id"] == "DS8-001"


def test_rejects_duplicate_or_incomplete_membership():
    row = {
        "session_id": "a",
        "capture_start_utc_ns": 1,
        "manifest_sha256": "a",
        "sample_rate_hz": 1,
    }
    with pytest.raises(ValueError, match="duplicate"):
        module.select({"dataset_id": "DS9", "captures": [row, row]}, 2)
    with pytest.raises(ValueError, match="insufficient"):
        module.select({"dataset_id": "DS9", "captures": [row]}, 2)
