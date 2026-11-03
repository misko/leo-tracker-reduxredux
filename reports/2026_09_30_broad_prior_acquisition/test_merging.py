import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import (
    Candidate, FilterState, GaussianComponent, ObservationFactor, Prediction,
)
from replay_merging import merge_update


def test_merge_integration_keeps_mass_and_shared_cross_covariance():
    p = np.eye(6)
    p[0,3] = p[3,0] = .4
    state = FilterState((GaussianComponent(1., np.zeros(6), p),))
    h = np.zeros((1,6)); h[0,0] = 1.; h[0,3] = .3
    factor = ObservationFactor(("a",), np.array([.2]), (
        Candidate("sat", .7, lambda _:Prediction(np.zeros(1),h,np.eye(1))),), .3, -1.)
    merged, updated, reduction, distortion = merge_update(state, factor, 4, 1)
    assert updated.retained_pre_normalization_mass == pytest.approx(1.)
    assert len(merged.components) == 1 and reduction.input_count == 2
    expected = sum(c.weight*c.mean for c in updated.state.components)
    np.testing.assert_allclose(merged.components[0].mean, expected)
    assert merged.components[0].covariance[0,3] != 0.
    assert distortion.maximum_absolute_log_error >= 0.
    assert merged.consumed_observation_ids == ("a",)
    with pytest.raises(ValueError, match="already consumed"):
        merge_update(merged, factor, 4, 1)
