import importlib.util
import sys
from pathlib import Path

import numpy as np


def subject():
    path = Path(__file__).parents[2] / "reports/2026_09_23_long_shared_epoch_position/fit.py"
    spec = importlib.util.spec_from_file_location("long_shared_epoch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_training_score_and_profiled_cfo_ignore_complementary_rows():
    module = subject()
    single_path = Path(__file__).parents[2] / "reports/2026_09_23_long_training_search/search.py"
    single = module.load_module(single_path, "shared_epoch_test_single")
    grid = np.arange(11, dtype=np.int64) * 1_000_000_000
    position = np.tile(np.asarray([7000.0, 0.0, 0.0]), (11, 1))
    velocity = np.column_stack((np.arange(11.0), np.zeros((11, 2))))
    training = np.asarray([True, False, True, False, True, False])

    def scan(held_delta):
        measured = np.arange(6.0) * 100.0
        measured[~training] += held_delta
        track = {
            "track_id": "track", "candidate_id": "candidate",
            "times_s": np.arange(6.0), "measured_hz": measured,
            "training_mask": training, "weight_s": 6,
            "grid_ns": grid, "position": position, "velocity": velocity,
        }
        return [{"session_id": "scan", "tracks": [track]}]

    before = module.score(single, scan(0.0), (0.0, 0.0), [0.0], 1.0)
    after = module.score(single, scan(1e7), (0.0, 0.0), [0.0], 1.0)
    assert before["penalized_objective_rmse_hz"] == after["penalized_objective_rmse_hz"]
    assert before["rows"][0]["tracks"][0]["frequency_offset_hz"] == (
        after["rows"][0]["tracks"][0]["frequency_offset_hz"]
    )
