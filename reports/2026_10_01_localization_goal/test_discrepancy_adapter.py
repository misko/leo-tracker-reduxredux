# ruff: noqa: I001
import numpy as np
from discrepancy_adapter import DiscrepancyLikelihood, DiscrepancyPort
from adapter import TrackPort
from physics import StateLayout
from test_acquisition_dot import fixture

from leo.analysis.robust_likelihood import student_t_logpdf


def test_zero_arm_preserves_scores_and_prediction():
    args = fixture(lambda east, north: .03)
    track, bank, config, height, _ = args
    base = TrackPort(track, bank, StateLayout(bank.norad_ids), config, height)
    modified = DiscrepancyPort(base, DiscrepancyLikelihood(*args, sigma=0.))
    state = np.zeros(7)
    np.testing.assert_allclose(modified.score_all(state), base.score_all(state), atol=1e-10)
    np.testing.assert_array_equal(modified.predict_selected(state, 0).covariance,
                                  base.predict_selected(state, 0).covariance)


def test_nonzero_prediction_covariance_matches_normalized_branch_density():
    args = fixture(lambda east, north: .03)
    track, bank, config, height, _ = args
    base = TrackPort(track, bank, StateLayout(bank.norad_ids), config, height)
    port = DiscrepancyPort(base, DiscrepancyLikelihood(*args, sigma=.5))
    state = np.zeros(7)
    prediction = port.predict_selected(state, 0)
    expected = student_t_logpdf(port.observation-prediction.mean, prediction.covariance, 4.)
    expected += np.log(config.signal_prior/port.candidate_count)
    np.testing.assert_allclose(port.score_selected(state, 0), expected, atol=1e-8)
    np.testing.assert_allclose(port.score_all(state)[-1], base.score_all(state)[-1], atol=1e-10)
    assert np.trace(prediction.covariance) > np.trace(base.predict_selected(state, 0).covariance)
