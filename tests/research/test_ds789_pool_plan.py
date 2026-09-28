import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ds789_pool_plan import layout  # noqa: E402


def example():
    return [
        {
            "dataset_id": f"DS{i}",
            "session_ids": [f"{i}a", f"{i}b"],
            "point": [float(i), -float(i), 0.1 * i, 0.2 * i],
        }
        for i in (7, 8, 9)
    ]


def test_excluded_dataset_cannot_change_position_starts_or_timings():
    groups = example()
    original = layout(groups, "DS8")
    changed = copy.deepcopy(groups)
    changed[1]["point"] = [float("nan")]
    changed[1]["session_ids"] = ["unread", "excluded", "data"]
    assert layout(changed, "DS8") == original
    assert original["session_ids"] == ["7a", "7b", "9a", "9b"]
    assert original["starts"][1]["x"] == pytest.approx([9.0, -9.0, 0.7, 1.4, 0.9, 1.8])
    assert groups == example()


def test_ambiguous_membership_and_malformed_starts_rejected():
    groups = example()
    with pytest.raises(ValueError, match="unknown"):
        layout(groups, "DS10")
    groups[2]["session_ids"][0] = "7a"
    with pytest.raises(ValueError, match="duplicate source"):
        layout(groups)
    groups = example()
    groups[0]["point"] = [1, 2]
    with pytest.raises(ValueError, match="dimensions"):
        layout(groups)
