import numpy as np
import pytest
from south_glrt_surface_probe import ALIAS_HZ, closest_alias, continuous_scores, select_rows


def test_continuous_phase_recovers_off_grid_frequency_and_alias():
    lags = np.arange(64) * 4.4e-6
    values = np.exp(2j * np.pi * 123.45 * lags)[None, :] * np.array([[1], [2j]])
    scores = continuous_scores(values, lags, [0., 123.45, 123.45 + ALIAS_HZ])
    assert scores[1] == pytest.approx(1.)
    assert scores[2] == pytest.approx(1.)
    assert scores[0] < scores[1]
    assert closest_alias(123.45 + ALIAS_HZ, 100.) == pytest.approx(123.45)


def test_zero_energy_and_shape_validation():
    np.testing.assert_array_equal(continuous_scores(np.zeros((2, 4)), np.arange(4), [1., 2.]), 0)
    with pytest.raises(ValueError):
        continuous_scores(np.zeros((2, 4)), np.arange(3), [1.])


def test_selection_requires_stability_positive_gain_and_distinct_groups():
    rows = [{"row": str(index), "group": str(group), "truth_satellite": "42",
             "stable_confident_match": stable, "path_attributed_data_gain": str(gain)}
            for index, (group, stable, gain) in enumerate(
                [(0, "True", 3), (0, "True", 2), (1, "False", 5),
                 (2, "True", 1), (3, "True", -1)])]
    assert [row["row"] for row in select_rows(rows, [42])] == ["0", "3"]
