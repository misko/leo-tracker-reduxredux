import numpy as np
import pytest
from finite_set_likelihood import prepare_finite_set_likelihood
from south_point_attribution import aggregate, integrate_prediction_path


def test_integrated_peak_attribution_closes_competitive_group_likelihood_difference():
    prepared = prepare_finite_set_likelihood([0., 90., 1200.], [0, 0, 1])
    truth = np.array([[200., 600.], [200., 600.], [1300., 800.]])
    south = truth + np.array([[-30., 20.], [-30., 20.], [40., -10.]])
    visible = np.ones_like(truth, dtype=bool)
    contribution = integrate_prediction_path(prepared, truth, south, visible, .2)
    values = [prepared.evaluate(prediction, visible, sigma_hz=200., detection_probability=.2,
                                clutter_rate=2.)["total_log_likelihood"]
              for prediction in (truth, south)]
    assert contribution.sum() == pytest.approx(values[1] - values[0], abs=1e-10)
    assert np.any(contribution > 0) and np.any(contribution < 0)


def test_aggregation_preserves_signed_contributions_not_only_winners():
    rows = aggregate(np.array([3., -2., 4.]), np.array([[0, 1], [0, 1], [1, 2]]))
    assert sum(row["gain"] for row in rows) == 5.
    assert sum(row["count"] for row in rows) == 3
