from hashlib import sha256
from importlib import import_module
from types import SimpleNamespace

import numpy as np
import pytest


trial = import_module("reports.ALGO08.single-core-2x.mirrored_causal_forecast_trial")


def test_rolling_state_applies_one_fixed_weight_to_both_state_vectors():
    latest = np.arange(6., 12.).reshape(2, 3)
    previous = np.arange(6.).reshape(2, 3)
    current = SimpleNamespace(sgp4_array=lambda *_: (np.array([0, 0]), latest, 2 * latest))
    older = SimpleNamespace(sgp4_array=lambda *_: (np.array([0, 1]), previous, 2 * previous))
    errors, position, velocity = trial.RollingState(current, older, .5).sgp4_array([], [])
    np.testing.assert_array_equal(errors, [0, 0])
    np.testing.assert_array_equal(position, [latest[0] + 3, latest[1]])
    np.testing.assert_array_equal(velocity, 2 * position)


def test_prediction_lock_rejects_changed_curves_before_decoding(tmp_path):
    path = tmp_path / "forecast.json"
    locked = b'{"causal_cutoff_utc_ns":42}'
    pin = sha256(locked).hexdigest()
    path.write_bytes(locked)
    assert trial.checked_lock(path, pin) == {"causal_cutoff_utc_ns": 42}
    path.write_bytes(b'{"causal_cutoff_utc_ns":43}')
    with pytest.raises(ValueError, match="pre-reveal lock"):
        trial.checked_lock(path, pin)
