import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
from ds7_candidate_generalization import compare_candidates


def test_alternative_selection_ignores_held_and_is_permutation_invariant():
    ids, train, held = (
        np.array([9, 3, 8]),
        np.array([0.0, -5.0, -5.0]),
        np.array([-10.0, -2.0, -7.0]),
    )
    original = compare_candidates(ids, train, held)
    changed = compare_candidates(ids, train, -held * 100)
    assert original["map_catalogue_id"] == changed["map_catalogue_id"] == 9
    assert original["runner_up_catalogue_id"] == changed["runner_up_catalogue_id"] == 3
    assert original["weights"] == changed["weights"]
    order = [2, 0, 1]
    permuted = compare_candidates(ids[order], train[order], held[order])
    for name in original:
        if name not in ("candidate_ids", "weights", "held_scores"):
            assert permuted[name] == pytest.approx(original[name])


def test_normalized_predictive_mixture_and_high_confidence_counterexample():
    result = compare_candidates([10, 20], np.log([0.999, 0.001]), np.log([0.1, 0.5]))
    assert result["full_held_log_score"] == pytest.approx(np.log(0.999 * 0.1 + 0.001 * 0.5))
    assert result["runner_up_held_minus_map"] == pytest.approx(np.log(5))
    assert result["alternative_mixture_held_minus_full"] > 0
    assert result["map_probability"] == pytest.approx(0.999)


def test_invisible_and_single_candidate_do_not_invent_a_comparison():
    result = compare_candidates([10, 20], [0, -np.inf], [-4, -2])
    assert result["visible_candidates"] == 1
    assert result["runner_up_catalogue_id"] is None
    assert result["alternative_mixture_held_minus_full"] is None
    with pytest.raises(ValueError):
        compare_candidates([10, 10], [0, 0], [-1, -1])
    with pytest.raises(ValueError):
        compare_candidates([10], [-np.inf], [-1])
