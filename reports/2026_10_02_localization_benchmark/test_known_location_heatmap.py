import models
import numpy as np
from evaluate import coordinates
from known_location_heatmap import ALIAS, intercept_losses, position_from_latlon


def test_known_location_roundtrips_coordinate_convention():
    location = [37.858988, -122.478103]
    np.testing.assert_allclose(coordinates(position_from_latlon(*location)), location, atol=1e-10)


def test_sorted_sweep_matches_exhaustive_alternative_scoring():
    groups = [
        (np.array([100.0, -230000.0, 100.0]), np.array([-120.0, 120.0, -120.0])),
        (np.array([]), np.array([])),
        (np.array([90000.0]), np.array([23.0])),
    ]
    intercepts = np.array([-1000, 0, 91000, ALIAS - 1, ALIAS + 100])
    for slope in (-200, -10, 0, 10, 200):
        brute = []
        for intercept in intercepts:
            costs = [
                models.rho(np.min(np.abs(models.circular(values - slope * times, intercept))))
                if len(values)
                else models.UNMATCHED_COST
                for values, times in groups
            ]
            brute.append(np.mean(costs))
        np.testing.assert_allclose(intercept_losses(groups, intercepts, slope), brute, atol=1e-6)


def test_intercept_alias_periodicity():
    groups = [(np.array([100, 1000, -3000]), np.array([2, 3, 4]))]
    np.testing.assert_allclose(
        intercept_losses(groups, [200], 3), intercept_losses(groups, [200 + ALIAS], 3), atol=1e-6
    )
