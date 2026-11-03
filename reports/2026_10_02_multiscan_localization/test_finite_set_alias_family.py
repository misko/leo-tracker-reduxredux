from types import SimpleNamespace

import numpy as np
import pytest
from finite_set_alias_family import FamilyGeometryData, fit_families


def source_data():
    return SimpleNamespace(
        times=np.array([0., 1., 9., 20.]),
        measured=np.array([1., 2., 3., 4.]),
        rf=np.ones(4), receiver=np.zeros(4), channel=np.zeros(4),
        group=np.array([0, 0, 0, 1]), margin=np.ones(4),
    )


def test_median_geometry_frozen_before_family_selection():
    from finite_set_fit import array_digest

    source = source_data()
    adapted = FamilyGeometryData(source, [0, 3])
    np.testing.assert_array_equal(adapted.times, [1, 20])
    np.testing.assert_array_equal(source.times, [0, 1, 9, 20])
    np.testing.assert_array_equal(adapted.measured, [1, 4])
    assert adapted.geometry_receipt["representative_row_count"] == 2
    assert adapted.geometry_receipt["fitted_array_hashes"]["times"] == array_digest(adapted.times)
    assert adapted.geometry_receipt["preselection_geometry"]["group_count"] == 2


@pytest.mark.parametrize("rows", [[0], [0, 0, 3], [-1, 3], [0, 4]])
def test_invalid_or_missing_group_representatives_rejected(rows):
    with pytest.raises(ValueError):
        FamilyGeometryData(source_data(), rows)


def test_subset_prediction_and_jacobian_match_original_median_geometry():
    from finite_set_fit import GroupMedianGeometryData
    from prediction_jacobian import paired_prediction_jacobian
    from prediction_plan import SharedPredictionPlan
    from test_staged_gradient import synthetic_orbital_data

    data, parameters = synthetic_orbital_data()
    data.group = np.arange(len(data.times))
    indices = np.array([0, 0, 1, 2, 2, 3])
    for name in ("times", "rf", "receiver", "group", "measured", "channel", "margin"):
        setattr(data, name, getattr(data, name)[indices])
    data.times[1] += 0.001
    representatives = np.array([1, 2, 4, 5])
    satellites = np.array([0, 2])
    expected, visible, jacobian = paired_prediction_jacobian(
        GroupMedianGeometryData(data), parameters,
        np.repeat(representatives, 2), np.tile(satellites, 4),
    )
    adapted = FamilyGeometryData(data, representatives)
    actual, actual_visible, actual_jacobian = SharedPredictionPlan(adapted, satellites).predict(
        parameters
    )
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual_visible, visible)
    weights = np.linspace(-1, 1, len(actual))
    np.testing.assert_allclose(
        actual_jacobian.transpose_multiply(weights), jacobian.transpose_multiply(weights),
    )


def test_all_banks_fit_with_frozen_priors_and_unresolved_preserved():
    calls = []

    def refiner(data, parameters, satellites, weights, likelihood, **kwargs):
        calls.append((parameters, satellites, kwargs))
        return {
            "objective": 1., "initial_objective": 2.,
            "selection_score": float(len(satellites)),
            "success": len(satellites) == 1,
        }

    source = {
        "full_bank": [0, 1],
        "finite_set_trials": [
            {"satellite_indices": [0], "parameters": [10.]},
            {"satellite_indices": [0, 1], "parameters": [20.]},
        ],
    }
    result = fit_families(FamilyGeometryData(source_data(), [0, 3]), source, refiner=refiner)
    assert len(calls) == 2
    assert not result["finite_set_selection"]["selection_resolved"]
    assert calls[0][2] == {
        "sigma_hz": 200., "tau_sigma_s": 1., "tau_bound_s": 3.,
        "slope_bound": 50., "budget_s": 15.,
    }
    np.testing.assert_array_equal(calls[1][0], [20.])
