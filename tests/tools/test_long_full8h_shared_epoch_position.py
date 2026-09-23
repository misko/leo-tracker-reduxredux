import importlib.util
import sys
from pathlib import Path

import numpy as np


def subject():
    path = Path(__file__).parents[2] / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py"
    spec = importlib.util.spec_from_file_location("full8h_shared_epoch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_training_score_and_cfo_ignore_complementary_rows():
    module = subject()
    single_path = Path(__file__).parents[2] / "reports/2026_09_23_long_training_search/search.py"
    single = module.load_module(single_path, "satellite_epoch_test_single")
    grid = np.arange(11, dtype=np.int64) * 1_000_000_000
    training = np.asarray([True, False, True, False, True, False])
    position = np.tile(np.asarray([7000.0, 0.0, 0.0]), (11, 1))
    velocity = np.column_stack((np.arange(11.0), np.zeros((11, 2))))

    def track(delta):
        measured = np.arange(6.0) * 100.0
        measured[~training] += delta
        return {
            "session_id": "scan",
            "track_id": "track",
            "candidate_id": "sat",
            "times_s": np.arange(6.0),
            "measured_hz": measured,
            "training_mask": training,
            "weight_s": 6,
            "grid_ns": grid,
            "position": position,
            "velocity": velocity,
        }

    before = module.score(single, [track(0.0)], (0.0, 0.0), {"scan": 0.0}, 1.0)
    after = module.score(single, [track(1e7)], (0.0, 0.0), {"scan": 0.0}, 1.0)
    assert before["penalized_objective_rmse_hz"] == after["penalized_objective_rmse_hz"]
    assert before["rows"][0]["frequency_offset_hz"] == after["rows"][0]["frequency_offset_hz"]


def test_bound_active_schur_freezes_only_outward_eta_steps():
    module = subject()
    blocks = {
        "upper_outward": (2.0, np.asarray([1.0, 0.0]), -2.0),
        "lower_inbound": (2.0, np.asarray([0.0, 1.0]), -1.0),
    }
    dp, de, frozen = module.bound_active_schur_step(
        np.diag([4.0, 3.0]),
        np.asarray([-2.0, 1.0]),
        blocks,
        {"upper_outward": 5.0, "lower_inbound": -5.0},
    )
    # Freezing the outward upper eta changes dp_x from the unconstrained 2/7
    # to the dense active-set solution 1/2. The lower-bound eta moves inward.
    np.testing.assert_allclose(dp, [0.5, -0.6])
    assert frozen == ("upper_outward",)
    np.testing.assert_allclose(de["upper_outward"], 0.0)
    np.testing.assert_allclose(de["lower_inbound"], 0.8)
