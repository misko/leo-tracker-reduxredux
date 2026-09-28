import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).with_name("prepare.py")
SPEC = importlib.util.spec_from_file_location("arm_ds89_prepare", PATH)
prepare = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(prepare)


def test_quartile_midpoints_are_deterministic_and_in_range():
    assert prepare.selected_indices(8) == [1, 3, 5, 7]
    assert prepare.selected_indices(2215) == [276, 830, 1384, 1938]
    with pytest.raises(ValueError, match="fewer than four"):
        prepare.selected_indices(3)


def test_real_plan_covers_every_ds8_ds9_capture_once():
    plan = prepare.make_plan()
    assert plan["schema"] == "ds7-large-arm-plan/v1"
    assert plan["dataset_capture_counts"] == {"DS8": 65, "DS9": 105}
    assert plan["expected_captures"] == 170
    assert plan["expected_visits"] == 680
    assert len(plan["captures"]) == 170
    assert {capture["dataset_id"] for capture in plan["captures"]} == {"DS8", "DS9"}
    assert all(len(capture["visit_indices"]) == 4 for capture in plan["captures"])
    assert all(len(set(capture["visit_indices"])) == 4 for capture in plan["captures"])
    assert all(max(capture["visit_indices"]) < capture["visits"] for capture in plan["captures"])
    prepare.validate_plan(plan)


def test_plan_validation_fails_closed_on_selection_change():
    plan = prepare.make_plan()
    plan["captures"][0]["visit_indices"][0] += 1
    with pytest.raises(ValueError, match="deterministic metadata-only selection"):
        prepare.validate_plan(plan)
