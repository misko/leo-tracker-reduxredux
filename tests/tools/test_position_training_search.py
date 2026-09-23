import importlib.util
from pathlib import Path

import numpy as np


def subject():
    path = Path(__file__).parents[2] / "tools/research/position_training_search.py"
    spec = importlib.util.spec_from_file_location("position_training_search", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bounded_fit_recovers_synthetic_position_without_escape():
    module = subject()
    target = np.array([37.85, -122.48])
    visited = []

    def objective(point):
        visited.append(point.copy())
        return float(np.sum((point - target) ** 2))

    fit = module.bounded_fit(objective, [37.8, -122.4])
    assert np.linalg.norm(np.array([fit["latitude_deg"], fit["longitude_deg"]]) - target) < 0.003
    assert module.inside_prior_intersection((fit["latitude_deg"], fit["longitude_deg"]))
    assert all(module.inside_prior_intersection(point) for point in visited)


def test_training_score_is_invariant_to_evaluation_frequency_mutation():
    module = subject()

    class Prediction:
        measured_hz = np.arange(8.0)
        training_mask = np.array([1, 0, 1, 0, 1, 1, 0, 0], dtype=bool)
        predictions_hz = np.zeros((2, 2, 8))
        visible = np.ones(2, dtype=bool)
        candidate_ids = np.array([1, 2])
        taus_s = np.array([-1.0, 1.0])

    first = module.score_prediction_training(Prediction())
    changed = Prediction()
    changed.measured_hz = Prediction.measured_hz.copy()
    changed.measured_hz[~Prediction.training_mask] = 1e9
    assert module.score_prediction_training(changed) == first
