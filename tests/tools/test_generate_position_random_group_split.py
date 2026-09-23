import importlib.util
from pathlib import Path


def subject():
    path = Path(__file__).parents[2] / "tools/research/generate_position_random_group_split.py"
    spec = importlib.util.spec_from_file_location("random_group_split", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_assignment_is_deterministic_and_keeps_groups_exclusive():
    module = subject()
    groups = [
        {
            "group_id": f"g{index}",
            "interval_start": f"2026-01-{index + 1:02d}T00:00:00Z",
            "session_count": size,
            "session_ids": [f"s{index}-{j}" for j in range(size)],
        }
        for index, size in enumerate([3, 4, 5, 6, 7, 8])
    ]
    first = module.assign_groups(groups, 17)
    assert first == module.assign_groups(groups, 17)
    assigned_groups = [group["group_id"] for rows in first.values() for group in rows]
    assert sorted(assigned_groups) == sorted(group["group_id"] for group in groups)
    assert len(assigned_groups) == len(set(assigned_groups))


def test_grouping_uses_fixed_nonoverlapping_utc_intervals():
    module = subject()
    scans = [
        {"session_id": "a", "captured_at": "2026-09-23T01:50:00Z", "nominal_capture_seconds": 300},
        {"session_id": "b", "captured_at": "2026-09-23T00:10:00Z", "nominal_capture_seconds": 300},
        {"session_id": "c", "captured_at": "2026-09-23T02:00:00Z", "nominal_capture_seconds": 300},
    ]
    groups = module.group_scans(scans)
    assert [group["session_ids"] for group in groups] == [["b", "a"], ["c"]]
    assert groups[0]["interval_end_exclusive"] == groups[1]["interval_start"]


def test_grouping_rejects_a_capture_that_crosses_a_boundary():
    module = subject()
    scans = [
        {
            "session_id": "crossing",
            "captured_at": "2026-09-23T01:59:00Z",
            "nominal_capture_seconds": 300,
        }
    ]
    try:
        module.group_scans(scans)
    except ValueError as error:
        assert "crosses a group boundary" in str(error)
    else:
        raise AssertionError("boundary-crossing capture was accepted")
