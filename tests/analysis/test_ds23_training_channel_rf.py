import numpy as np
import pytest

from ds23_training_channel_rf import TrainingChannelWorkspace, projected_frame_gains


def workspace(samples=None):
    if samples is None:
        rng = np.random.default_rng(731)
        samples = rng.normal(size=20000) + 1j * rng.normal(size=20000)
    segments = [np.arange(a, a + 1200) for a in [200, 3600, 7000, 10400, 13800]]
    return TrainingChannelWorkspace(samples, 2500000., 'lower', 23.2, segments)


def test_no_objective_can_read_outside_the_training_IQ():
    first = workspace()
    used = np.zeros(len(first.y), bool)
    used[np.concatenate(first.frames)] = True
    changed = first.y.copy()
    changed[~used] += 1e6 + 2e6j
    second = workspace(changed)
    parameters = [12345., .13, 6.4]
    for key in ['score', 'gradient_score', 'normal', 'rhs', 'raw_energy']:
        np.testing.assert_array_equal(first.statistics(parameters)[key], second.statistics(parameters)[key])
    np.testing.assert_array_equal(first.evaluate([12345., 12400.], .13, 6.4, control=True),
        second.evaluate([12345., 12400.], .13, 6.4, control=True))


def test_projected_score_gradient_matches_finite_differences():
    ws = workspace()
    p = np.array([12345.2, .133, 6.43])
    result = ws.statistics(p)
    # The interpolant is piecewise linear. Small steps stay inside its knots.
    for k, step in enumerate([1e-3, 1e-7, 1e-6]):
        delta = np.zeros(3)
        delta[k] = step
        numeric = (ws.statistics(p + delta, derivatives=False)['score']
            - ws.statistics(p - delta, derivatives=False)['score']) / (2 * step)
        np.testing.assert_allclose(result['gradient_score'][k] / ws.parameter_scale[k],
            numeric, rtol=2e-4, atol=2e-10)


def test_nonflat_channel_carrier_epoch_and_rate_recovery():
    base = workspace()
    truth = np.array([12345.25, .123, 6.4])
    columns = base.columns(truth)
    rng = np.random.default_rng(831)
    y = np.zeros_like(base.y)
    for k, ix in enumerate(base.frames):
        gain = rng.normal(size=8) + 1j * rng.normal(size=8)
        y[ix] = columns[ix] @ gain + (k + 2j)
    ws = workspace(y)
    fit = ws.fit_from_training_seed(dict(CFO_hz=truth[0]-17,
        offset_samples=truth[1]+.05, modulation_ppm=truth[2]+.4), truth[0]-17, iterations=24)
    assert fit['score'] > 1-1e-7
    assert abs(fit['CFO_hz']-truth[0]) < .1
    assert abs(fit['offset_samples']-truth[1]) < .001
    assert abs(fit['modulation_ppm']-truth[2]) < .02
    assert fit['margin'] > .1


def test_training_segments_must_be_disjoint():
    with pytest.raises(ValueError, match='disjoint'):
        TrainingChannelWorkspace(np.zeros(20000), 2500000., 'lower', 23.2,
            [np.arange(200, 1200)] * 5)


def test_complex_projection_variance_matches_direct_gaussian_sampling():
    rng = np.random.default_rng(3321)
    coefficient = np.outer(np.array([1, 2j, -1, 1j, 2, 1-1j]), np.array([1, 1j]))
    covariance = np.array([[2., .8+.7j], [.8-.7j, 3.]])
    repeated = np.tile(covariance, (len(coefficient), 1, 1))
    training = np.array([True, True, True, True, False, False])
    result = projected_frame_gains(coefficient, repeated, training)
    _, _, vh = np.linalg.svd(coefficient[training], full_matrices=False)
    direction = vh[0].conj()
    expected = float((direction @ covariance @ direction.conj()).real)
    wrong_orientation = float((direction.conj() @ covariance @ direction).real)
    assert abs(expected-wrong_orientation) > 1.
    np.testing.assert_allclose(result['variance'], expected)
    noise = (rng.normal(size=(40000, 2))+1j*rng.normal(size=(40000, 2)))/np.sqrt(2)
    correlated = noise @ np.linalg.cholesky(covariance).T
    measured = float(np.mean(abs(correlated @ direction)**2))
    np.testing.assert_allclose(measured, expected, rtol=.025)
