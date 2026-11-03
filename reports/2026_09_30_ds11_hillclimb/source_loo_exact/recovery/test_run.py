import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("recovery_run_test", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("field,value", [("stable_by_established_limits", False),
    ("newton_solve_available", False), ("newton_en_displacement_m", .011),
    ("newton_time_displacement_s", -1.1e-5)])
def test_unreliable_or_material_precision_correction_blocks_fit(field, value):
    row = dict(finite_checks_passed=True, numerical=dict(stable_by_established_limits=True,
        newton_solve_available=True, newton_en_displacement_m=.0001,
        newton_time_displacement_s=1e-8))
    assert runner.precision_passed(row)
    changed = copy.deepcopy(row)
    changed["numerical"][field] = value
    assert not runner.precision_passed(changed)
