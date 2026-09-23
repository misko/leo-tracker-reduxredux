import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).parents[2] / "tools/research/evaluate_longarc_phase.py"
SPEC = importlib.util.spec_from_file_location("evaluate_longarc_phase", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_outer_held_mutation_cannot_change_fit():
    time = np.arange(8.0)
    candidates = np.vstack([2 * time, 3 * time])
    training = np.array([True, False, True, False, True, False, True, False])
    observed = candidates[1] + 7 - 0.2 * time
    first = MODULE.fit_candidate_affine(observed, candidates, time, training)
    observed[~training] += 1e9
    second = MODULE.fit_candidate_affine(observed, candidates, time, training)
    assert first == second


def test_equal_visit_rms_does_not_pool_frame_counts():
    answer = MODULE.equal_visit_rms([np.array([3.0]), np.full(20, 4.0)])
    assert answer == np.sqrt((9 + 16) / 2)


def test_held_glrt_value_cannot_choose_response_alias():
    frame = {
        "frame": {
            "odd": {"absolute_cfo_hz": -95_000.0, "search_boundary": False}
        }
    }
    observation = {
        "historical_rf_normalization_scale": 0.98,
        "historical_pilot_alias_period_hz": (1 / 4.4e-6) * 0.98,
        "historical_pilot_alias_index": 1,
        "normalized_cfo_hz": 1.0,
    }
    first = MODULE.normalized_frame_cfo(frame, observation, "odd", reject_boundary=False)
    observation["normalized_cfo_hz"] = 1e9
    second = MODULE.normalized_frame_cfo(frame, observation, "odd", reject_boundary=False)
    assert first == second
