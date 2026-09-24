import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "reports/2026_09_23_long_inventory_complete/split.py"
SPEC = importlib.util.spec_from_file_location("long_split", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def inventory():
    groups, rows = [], []
    for day, hour in [(21, 0), (21, 8), (21, 16), (22, 0), (22, 8)]:
        key = f"2026-09-{day}T{hour:02d}:00:00+00:00"
        ids = [f"{key}-{index}" for index in range(40)]
        groups.append({"utc_8h_start": key, "session_ids": ids})
        rows.extend(
            {"session_id": sid, "nominal_duration_s": 300, "contained_nominal_interval": True}
            for sid in ids
        )
    return {
        "window_start": "2026-09-20T16:35:28+00:00",
        "window_end_exclusive": "2026-09-23T16:35:28+00:00",
        "utc_8h_groups": groups,
        "scans": rows,
        "excluded_ids": [],
    }


def test_deterministic_disjoint_whole_groups_and_test_exposure():
    source = inventory()
    result = MODULE.assign(source)
    assert result == MODULE.assign(source)
    parts = result["partitions"]
    assert [len(parts[p]["session_ids"]) for p in ("train", "validation", "test")] == [80, 80, 40]
    assert not set(parts["test"]["groups"]) & MODULE.EXPOSED
    assert len({sid for part in parts.values() for sid in part["session_ids"]}) == 200


def test_reject_crossing_capture():
    source = inventory()
    source["scans"][0]["contained_nominal_interval"] = False
    with pytest.raises(ValueError, match="crossing"):
        MODULE.assign(source)


def test_reject_excluded_capture():
    source = inventory()
    source["excluded_ids"] = [source["scans"][0]["session_id"]]
    with pytest.raises(ValueError, match="excluded"):
        MODULE.assign(source)
