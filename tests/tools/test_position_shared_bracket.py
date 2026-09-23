import importlib.util
from pathlib import Path

import numpy as np


def subject():
    path = Path(__file__).parents[2] / "tools/research/position_shared_bracket.py"
    spec = importlib.util.spec_from_file_location("position_shared_bracket", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Grouped:
    @staticmethod
    def aggregate(rows, field, loss, weighting):
        del loss, weighting
        return float(np.sqrt(np.mean([row["score"][field] ** 2 for row in rows])))


def test_shared_tau_recovery_across_tracks():
    module = subject()
    profiles = [
        [{"training_rms_hz": 5.0}, {"training_rms_hz": 0.0}, {"training_rms_hz": 4.0}],
        [{"training_rms_hz": 8.0}, {"training_rms_hz": 1.0}, {"training_rms_hz": 3.0}],
    ]
    selected, _ = module.select_scan_tau(Grouped, profiles, [1, 1], "capped800")
    assert selected == 1


def test_training_profiles_ignore_heldout_mutation():
    module = subject()

    class Prediction:
        measured_hz = np.arange(8.0)
        training_mask = np.array([1, 0, 1, 0, 1, 1, 0, 0], dtype=bool)
        predictions_hz = np.zeros((2, 3, 8))
        visible = np.ones(2, dtype=bool)
        candidate_ids = np.array([1, 2])
        taus_s = np.array([-0.1, 0.0, 0.1])

    first = module.profile_track_by_tau(Prediction())
    changed = Prediction()
    changed.measured_hz = Prediction.measured_hz.copy()
    changed.measured_hz[~Prediction.training_mask] = 1e9
    assert module.profile_track_by_tau(changed) == first
