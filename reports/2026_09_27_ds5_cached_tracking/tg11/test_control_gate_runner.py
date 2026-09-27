"""Scientific stage advancement cannot hide failed or incomplete inventory."""

import importlib.util
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tg11_control_gate_runner", HERE / "run_control_gate.py")
RUNNER = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = RUNNER
spec.loader.exec_module(RUNNER)


@pytest.mark.parametrize("status,rows,expected,stable", [
    ("failed", [{"passed": True}], 1, True),
    ("timed_out_partial", [{"passed": True}], 1, True),
    ("complete", [{"passed": True}], 2, True),
    ("complete", [{"passed": False}], 1, True),
    ("complete", [{"passed": True}], 1, False),
])
def test_any_failed_gate_prevents_real_replay(status, rows, expected, stable):
    assert not RUNNER.gate_passed(status, rows, expected, stable)


def test_complete_fixed_inventory_is_required():
    assert RUNNER.gate_passed("complete", [{"passed": True}] * 42, 42, True)
    assert not RUNNER.gate_passed("complete", [{"passed": True}] * 41, 42, True)


def test_complete_key_uses_receiver_and_recording_identities():
    case = RUNNER.dataset.controls()[0]
    key = RUNNER.make_key(case, 1)
    assert key.receiver == 1
    assert key.continuity_epoch == case.session
    assert key.tuning_identity == case.tuning_identity
    assert key.calibration_identity == case.calibration_identity
