import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("restart_test", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("field,value", [("success", True), ("qualified", True),
    ("boundary", True), ("gradient_max_abs", 0.011), ("gradient_max_abs", None),
    ("gradient_audit_max_abs", 0.021), ("gradient_audit_max_abs", float("nan"))])
def test_only_failed_stationary_interior_fits_are_eligible(field, value):
    fold = dict(x=[1., 2., 0.], retained_score=-100., optimizer=dict(
        success=False, qualified=False, boundary=False,
        gradient_max_abs=0.001, gradient_audit_max_abs=0.001))
    assert runner.eligible(fold)
    changed = copy.deepcopy(fold)
    changed["optimizer"][field] = value
    assert not runner.eligible(changed)
