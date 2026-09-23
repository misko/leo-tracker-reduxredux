import importlib.util
import sys
from pathlib import Path

import numpy as np


def subject():
    path = (
        Path(__file__).parents[2]
        / "reports/2026_09_23_long_training_search_multi/search.py"
    )
    spec = importlib.util.spec_from_file_location("long_training_search_multi", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_combined_score_weights_scan_objectives_by_track_duration():
    module = subject()

    class FakeSingle:
        @staticmethod
        def score_point(prepared, candidate_ids, latitude, longitude, include_evaluation):
            del candidate_ids, latitude, longitude, include_evaluation
            return prepared[0], [{"track_id": "track"}]

    sessions = [
        {"session_id": "a", "prepared": [3.0], "candidate_ids": [], "weight": 1},
        {"session_id": "b", "prepared": [4.0], "candidate_ids": [], "weight": 3},
    ]
    score, rows = module.combined_score(FakeSingle(), sessions, 0.0, 0.0)
    np.testing.assert_allclose(score, np.sqrt((1 * 3.0**2 + 3 * 4.0**2) / 4))
    assert [row["session_id"] for row in rows] == ["a", "b"]
