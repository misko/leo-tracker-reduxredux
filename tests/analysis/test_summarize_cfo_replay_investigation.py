from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

_PATH = Path("tools/summarize_cfo_replay_investigation.py")
_SPEC = importlib.util.spec_from_file_location("summarize_cfo_replay_investigation", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_raw_points_select_only_glrt64_and_alias_lift_is_exact() -> None:
    pilot = {
        "detections": [
            {
                "time_s": 1.25,
                "candidates": [
                    {
                        "scores": [
                            {"method": "anchor8", "tracking_cfo_hz": -9.0},
                            {"method": "glrt64", "tracking_cfo_hz": 12_345.0},
                        ]
                    }
                ],
            }
        ]
    }
    times, frequencies = _MODULE._raw_points(pilot)
    assert times.tolist() == [1.25]
    assert frequencies.tolist() == [12_345.0]

    model = {
        "start_s": 1.0,
        "end_s": 2.0,
        "reference_time_s": 1.0,
        "coefficients_hz": [100.0, 1_000.0],
    }
    base_times, base = _MODULE._model_values(model)
    lifted_times, lifted = _MODULE._model_values(model, 2)
    assert np.array_equal(base_times, lifted_times)
    assert np.allclose(lifted - base, 2 * _MODULE.ALIAS_SPACING_HZ)
