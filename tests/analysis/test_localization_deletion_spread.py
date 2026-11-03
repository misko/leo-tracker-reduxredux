import numpy as np
import pytest

from leo.analysis.localization_deletion_spread import deletion_spread


def test_sample_mean_jackknife_matches_analytic_sampling_covariance():
    observations = np.array([[1., 2.], [2., -1.], [-3., 5.], [4., 3.], [-2., -2.]])
    mean = observations.mean(axis=0)
    deleted = np.array([np.delete(observations, i, axis=0).mean(axis=0)
                        for i in range(len(observations))])
    expected = np.cov(observations, rowvar=False, ddof=1)/len(observations)
    np.testing.assert_allclose(deletion_spread(deleted-mean), expected, rtol=1e-12)
    transform = np.array([[2., .5], [-1., 3.]])
    np.testing.assert_allclose(deletion_spread((deleted-mean)@transform.T+10.),
                               transform@expected@transform.T, rtol=1e-12)


def test_singular_spread_stays_singular_and_invalid_data_rejected():
    np.testing.assert_equal(deletion_spread(np.ones((4, 2))), np.zeros((2, 2)))
    for values in [np.zeros((1, 2)), np.zeros((4, 3)), [[0., 1.], [np.nan, 0.]]]:
        with pytest.raises(ValueError):
            deletion_spread(values)
