import numpy as np
import pytest
from scipy.linalg import solve_triangular

from tools.pipeline_eval.variants import innovation_noise as noise
from tools.pipeline_eval.variants import robust_em as dense


@pytest.mark.parametrize("times", [[0.0], [0.0, 0.000001, 0.04, 1.0, 150.0], np.arange(71) * 0.23])
@pytest.mark.parametrize("correlated", [0.0, 200.0])
def test_scalar_innovations_equal_the_dense_whitening_for_vectors_and_batches(times, correlated):
    t = np.array(times)
    covariance = correlated**2 * np.exp(-abs(t[:, None] - t) / 4.0) + np.eye(len(t)) * 150**2
    reference = solve_triangular(np.linalg.cholesky(covariance), np.eye(len(t)), lower=True)
    op = noise.InnovationFilter(t, 150.0, correlated, 4.0)
    data = np.random.default_rng(93).normal(size=(len(t), 13))
    np.testing.assert_allclose(op @ data, reference @ data, atol=1e-14)
    np.testing.assert_allclose(data.T @ op.T, data.T @ reference.T, atol=1e-14)
    np.testing.assert_allclose(op @ data[:, 1], reference @ data[:, 1], atol=1e-14)
    np.testing.assert_allclose(op.sum(axis=1), reference.sum(axis=1), atol=1e-14)
    assert op.nbytes == (5 * len(t) - 1) * 8


def test_retained_native_track_samples_duplicate_precedence_and_curvature_are_identical():
    arc = dict(
        receiver=2,
        channel=6,
        rf_hz=11.7e9,
        times=[1.0, 8.0, 20.0, 24.0, 25.0],
        values=[360.0, 100.0, 2700.0, 2540.0, 2480.0],
    )
    partial = dict(arc, times=[1.0, 8.0, 20.0, 26.0], values=[360.0, 100.0, 2700.0, 1000.0])
    document = dict(duration_s=30, tracks=[partial, arc, dict(arc, channel=1)])
    a, metrics_a = dense.observations(document)
    b, metrics_b = noise.observations(document)
    assert {k: metrics_b[k] for k in metrics_a} == metrics_a
    assert len(a) == len(b) == 2 and metrics_a["undersized_points_excluded"] == 1
    for prior, after in zip(a, b, strict=True):
        assert (prior.curved, prior.lane, prior.rf) == (after.curved, after.lane, after.rf)
        np.testing.assert_array_equal(prior.hz, after.hz)
        np.testing.assert_array_equal(prior.t, after.t)
        np.testing.assert_array_equal(prior.drift, after.drift)
        np.testing.assert_allclose(prior.whiten @ prior.hz, after.whiten @ after.hz)
    for wrong in ([1, 1, 2], [2, 1], [np.nan, 0]):
        with pytest.raises(ValueError):
            noise.InnovationFilter(wrong, 150, 200, 4)
