from types import SimpleNamespace

import numpy as np
import pytest
from finite_set_likelihood import prepare_finite_set_likelihood
from wrong_solution_attribution import gap_bins, group_metadata, weighted_residual_summary


def test_group_bins_conserve_signed_loss_gap():
    prepared = prepare_finite_set_likelihood([1., 2., 3., 4.], [0, 0, 1, 2])
    data = SimpleNamespace(receiver=np.array([0, 0, 1, 0]), channel=np.array([1, 1, 2, 1]),
                           times=np.array([0., 0., 30., 40.]))
    metadata = group_metadata(data, prepared)
    actual = gap_bins(np.array([10., -20., 4.]), metadata)
    assert sum(row["free_advantage_nll"] for row in actual) == -6
    assert sum(row["groups"] for row in actual) == 3
    data.times[1] = 1
    with pytest.raises(ValueError, match="group-inconsistent"):
        group_metadata(data, prepared)


def test_posterior_residual_summary_keeps_weight_semantics():
    actual = weighted_residual_summary(np.array([-1., 3.]), np.array([0.25, 0.75]))
    assert actual == {"support": 1., "mean_hz": 2., "rms_hz": np.sqrt(7)}
    assert weighted_residual_summary(np.array([5.]), np.array([0.]))["mean_hz"] is None
