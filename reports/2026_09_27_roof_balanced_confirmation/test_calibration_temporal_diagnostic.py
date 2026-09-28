from types import SimpleNamespace

import numpy as np
import pytest

from calibration_temporal_diagnostic import detection_predictions, summarize_tracks


def test_detection_predictions_marginalize_fixed_prior():
    layout = SimpleNamespace(size=2, detection_size=1)
    track = SimpleNamespace(
        detection_design=np.array([[[1.], [2.]], [[-1.], [-2.]]]),
        log_weights=np.log([.25, .75]))
    candidate, marginal = detection_predictions([1., 0.], track, layout)
    assert marginal == pytest.approx(np.array([.25, .75]) @ candidate)


def test_summary_subtracts_shared_identity_covariance():
    # Observed residual product equals the covariance induced solely by the
    # shared two-candidate identity, so the adjusted adjacent product is zero.
    candidate = np.array([[.8, .8], [.2, .2]])
    record = dict(matched=[1., 1.], marginal_probability=[.5, .5],
                  candidate_probability=candidate, weights=[.5, .5],
                  times_s=[0., 1.])
    result = summarize_tracks([record])
    assert result["adjacent_raw_standardized_covariance_ratio"] == pytest.approx(1.)
    # Observed product=.25 and shared-identity covariance=.09.
    assert result["adjacent_identity_adjusted_standardized_covariance_ratio"] == pytest.approx(.64)
    assert result["track_residual_sum_dispersion_ratio"] > 0


def test_summary_orders_timestamps_and_rejects_bad_weights():
    record = dict(matched=[0., 1., 0.], marginal_probability=[.4, .5, .6],
                  candidate_probability=[[.4, .5, .6]], weights=[1.],
                  times_s=[2., 0., 1.])
    result = summarize_tracks([record])
    assert result["adjacent_pairs"] == 2
    bad = dict(record, weights=[.9])
    with pytest.raises(ValueError):
        summarize_tracks([bad])
