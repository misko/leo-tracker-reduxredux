import importlib.util
import sys
from pathlib import Path

import numpy as np


def subject():
    path = (
        Path(__file__).parents[2] / "reports/2026_09_23_long_second8h_training_baseline/search.py"
    )
    spec = importlib.util.spec_from_file_location("second8h_baseline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_combined_score_matches_serial_weighted_pool():
    module = subject()

    class Scorer:
        @staticmethod
        def score_point(prepared, _candidate_ids, latitude, longitude, include_evaluation):
            assert not include_evaluation
            value = prepared[0]["base"] + latitude - longitude
            return value, [{"training_rms_hz": value}]

    sessions = [
        {"session_id": "a", "prepared": [{"base": 2.0}], "candidate_ids": [], "weight": 3},
        {"session_id": "b", "prepared": [{"base": 5.0}], "candidate_ids": [], "weight": 7},
    ]
    actual, rows = module.combined_score(Scorer(), sessions, 1.0, 0.5)
    expected = np.sqrt((3 * 2.5**2 + 7 * 5.5**2) / 10)
    assert actual == expected
    assert [row["session_id"] for row in rows] == ["a", "b"]
