import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from ds7_shared_slope_shadow import SharedSlope, fit  # noqa: E402


def example():
    time = np.arange(12, dtype=float) * 5
    return {
        "track_id": "a",
        "mask": np.arange(12) % 3 != 2,
        "column": time,
        "y": 33 - 1.2 * time,
        "prediction": np.array([np.zeros(12), time * 0.5]),
        "visible": np.array([True, True]),
        "catalogue_size": 2,
    }


def test_full_mixture_gradient_and_held_independence():
    original = example()
    changed = copy.deepcopy(original)
    changed["y"][~changed["mask"]] += 20000
    a, b = SharedSlope([original]), SharedSlope([changed])
    for slope in (-0.5, 0, 0.5):
        expected = (
            a.evaluate(slope + 1e-4)["training_log_score"]
            - a.evaluate(slope - 1e-4)["training_log_score"]
        ) / 2e-4
        assert a.evaluate(slope)["gradient"] == pytest.approx(expected, abs=1e-5)
        assert a.evaluate(slope) == b.evaluate(slope)


def test_known_slope_recovery_with_single_nominee_and_no_bound():
    track = example()
    track["prediction"] = track["prediction"][:1]
    track["visible"] = np.array([True])
    track["catalogue_size"] = 1
    shadow = SharedSlope([track])
    result = fit(shadow, None)
    slope = result["selected"]["slope_native_hz_s"]
    assert slope == pytest.approx(-1.2, abs=1e-5)
    assert (
        shadow.evaluate(slope, held=True)["held_log_score"]
        > shadow.evaluate(0, held=True)["held_log_score"]
    )
