import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).parents[2] / "tools" / "polish_regional_doppler.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("polish_regional_doppler", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_training_episode_gate_is_inclusive_and_training_only():
    answer = module.training_episode_gate(
        np.array([0.95, 0.99, 0.94]),
        np.array([500.0, 501.0, 10.0]),
        0.95,
        500.0,
    )
    np.testing.assert_array_equal(answer, [True, False, False])


@pytest.mark.parametrize("weight,rms", [(-0.1, 500.0), (1.1, 500.0), (0.95, 0.0)])
def test_training_episode_gate_rejects_invalid_settings(weight, rms):
    with pytest.raises(ValueError, match="training-only episode gate"):
        module.training_episode_gate([], [], weight, rms)


def test_candidate_elevation_uses_receiver_up():
    receiver = np.array([1.0, 0.0, 0.0])
    assert module.candidate_elevation_deg([2.0, 0.0, 0.0], receiver, receiver) == 90
    assert module.candidate_elevation_deg([1.0, 1.0, 0.0], receiver, receiver) == 0
