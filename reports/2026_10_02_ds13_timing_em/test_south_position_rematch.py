from types import SimpleNamespace

import numpy as np
import pytest
import south_position_rematch as rematcher


def fixture():
    data = SimpleNamespace(numbers=np.array([123, 456]))
    fit = {"parameters": [1.0, 2.0, 0, 0, 0, 0, 0, 0],
           "detection_probability": 0.08}
    profile = {"session": "test", "satellite_indices": [1], "catalog_numbers": [456],
               "detection_probability": 0.08,
               "positions": [{"label": "truth", "fixed_position_km": [1.0, 2.0],
                              "best": fit}]}
    return data, profile


def test_sealed_position_catalogue_probability_bindings():
    data, profile = fixture()
    _, parameters, satellites, probability = rematcher.profile_start(
        profile, "test", "truth", data)
    np.testing.assert_array_equal(parameters[:2], [1, 2])
    np.testing.assert_array_equal(satellites, [1])
    assert probability == 0.08
    profile["positions"][0]["best"]["parameters"][0] = 3
    with pytest.raises(ValueError, match="fixed position"):
        rematcher.profile_start(profile, "test", "truth", data)


def test_probability_mismatch_rejected():
    data, profile = fixture()
    profile["positions"][0]["best"]["detection_probability"] = 0.1
    with pytest.raises(ValueError, match="probability"):
        rematcher.profile_start(profile, "test", "truth", data)


def test_best_finite_keeps_lower_unconverged_and_preserves_incumbent():
    baseline = {"penalized_objective": 10.0, "satellite_indices": [1],
                "move": "baseline", "fit": {"success": True}}
    failed = {"penalized_objective": 9.0, "satellite_indices": [2],
              "move": "swap", "fit": {"success": False}}
    assert rematcher.best_finite([baseline, failed]) is failed
    failed["penalized_objective"] = 11
    assert rematcher.best_finite([baseline, failed]) is baseline


def test_symmetric_cases_use_identical_rules():
    assert rematcher.LABELS == ("truth", "S-500m")
    assert 0 < rematcher.BUDGET_S <= 120
    data, profile = fixture()
    point = dict(profile["positions"][0], label="S-500m")
    profile["positions"].append(point)
    first = rematcher.profile_start(profile, "test", "truth", data)
    second = rematcher.profile_start(profile, "test", "S-500m", data)
    np.testing.assert_array_equal(first[2], second[2])
    assert first[3] == second[3]
