import numpy as np
import pytest

from ds23_common_receiver_clock import loss, fit, predict, project_components, validate, align_frame_phase_branch


def scene():
    rng = np.random.default_rng(337)
    t = np.arange(36)/750
    covariance = np.array([[.006, .002+.001j], [.002-.001j, .008]])
    va = np.tile(covariance, (len(t), 1, 1))
    vb = va*1.2
    tx = np.exp(1j*rng.uniform(-np.pi, np.pi, (len(t), 2)))
    native = np.array([2000., 2020.])
    physical = 2034.
    ratio = np.array([.8+.2j, .9-.1j])
    rotation = ratio[None]*np.exp(2j*np.pi*(physical-native)[None]*t[:, None])
    def noise(cov):
        z = (rng.normal(size=(len(t), 2))+1j*rng.normal(size=(len(t), 2)))/np.sqrt(2)
        return z@np.linalg.cholesky(cov).T
    return t, tx+noise(covariance), rotation*tx+noise(covariance*1.2), va, vb, native


@pytest.mark.parametrize('mode', ['common', 'separate', 'independent'])
def test_full_complex_covariance_NLL_gradient_matches_finite_differences(mode):
    t, a, b, va, vb, native = scene()
    p = np.array([.8, .2, .9, -.1, 34., -3., -4.]) if mode == 'common' else np.array([.8, .2, .9, -.1, 34., 14., -3., -4.])
    _, gradient = loss(p, t, a, b, va, vb, native, mode, gradient=True)
    for k in range(len(p)):
        step = np.zeros_like(p)
        step[k] = 1e-6
        finite = (loss(p+step, t, a, b, va, vb, native, mode)
            - loss(p-step, t, a, b, va, vb, native, mode))/(2e-6)
        np.testing.assert_allclose(gradient[k], finite, rtol=2e-5, atol=2e-5)


def test_common_clock_recovers_one_physical_contrast_and_predicts_random_TX_frames():
    t, a, b, va, vb, native = scene()
    train = np.arange(len(t)) % 2 == 0
    common = fit(t[train], a[train], b[train], va[train], vb[train], native)
    independent = fit(t[train], a[train], b[train], va[train], vb[train], native, mode='independent')
    assert common['converged']
    np.testing.assert_allclose(common['corrected_RX_delta_hz'], 2034., atol=2.)
    assert abs(np.diff(common['corrected_RX_delta_hz'])[0]) < 1e-10
    assert predict(common, t[~train], a[~train], b[~train], va[~train], vb[~train]) < predict(
        independent, t[~train], a[~train], b[~train], va[~train], vb[~train])-20


def test_projected_covariance_matches_direct_correlated_complex_sampling():
    rng = np.random.default_rng(171)
    coefficients = rng.normal(size=(12, 4))+1j*rng.normal(size=(12, 4))
    m = rng.normal(size=(4, 4))+1j*rng.normal(size=(4, 4))
    covariance = m@m.conj().T+.1*np.eye(4)
    train = np.arange(12) % 2 == 0
    result = project_components(coefficients, np.tile(covariance, (12, 1, 1)), train, 2)
    z = (rng.normal(size=(50000, 4))+1j*rng.normal(size=(50000, 4)))/np.sqrt(2)
    noise = z@np.linalg.cholesky(covariance).T
    propagated = noise@result['projection'].T
    measured = propagated.T@propagated.conj()/len(z)
    np.testing.assert_allclose(measured, result['covariance'][0], atol=.12, rtol=.025)
    assert abs(result['covariance'][0, 0, 1]) > .1


def test_density_scale_and_off_diagonal_covariance_are_respected():
    t, a, b, va, vb, native = scene()
    first = fit(t[:20], a[:20], b[:20], va[:20], vb[:20], native)
    factor = np.array([2., 3.])
    scaled = fit(t[:20], a[:20]*factor, b[:20]*factor,
        va[:20]*factor[None, :, None]*factor[None, None, :],
        vb[:20]*factor[None, :, None]*factor[None, None, :], native)
    before = predict(first, t[20:], a[20:], b[20:], va[20:], vb[20:])
    after = predict(scaled, t[20:], a[20:]*factor, b[20:]*factor,
        va[20:]*factor[None, :, None]*factor[None, None, :],
        vb[20:]*factor[None, :, None]*factor[None, None, :])
    np.testing.assert_allclose(after-before, 2*len(t[20:])*np.log(factor).sum(), atol=.001)


def test_channel_directions_and_covariance_do_not_use_held_coefficients():
    rng = np.random.default_rng(141)
    c = rng.normal(size=(12, 4))+1j*rng.normal(size=(12, 4))
    covariance = np.tile(np.eye(4), (12, 1, 1))
    train = np.arange(12) % 2 == 0
    first = project_components(c, covariance, train, 2)
    c[~train] += 1000*(1+2j)
    second = project_components(c, covariance, train, 2)
    np.testing.assert_array_equal(first['projection'], second['projection'])
    np.testing.assert_array_equal(first['covariance'], second['covariance'])


def test_non_Hermitian_or_nonpositive_covariance_fails_explicitly():
    t, a, b, va, vb, _ = scene()
    va[0, 0, 1] += .1j
    with pytest.raises(ValueError, match='Hermitian'):
        validate(t, a, b, va, vb)


def test_pilot_CFO_alias_cannot_be_removed_before_frame_phase_comparison():
    pilot_period = 1/4.4e-6
    raw = np.array([425800., 425800.+pilot_period+29.])
    physical = 425825.
    correction = (physical-raw+375) % 750-375
    old = (raw+pilot_period/2) % pilot_period-pilot_period/2+correction
    np.testing.assert_allclose(old[1]-old[0], -22.7272727273, atol=1e-7)
    corrected = (raw+correction+375) % 750-375
    np.testing.assert_allclose(corrected[1]-corrected[0], 0., atol=1e-7)


def test_exact_branch_alignment_preserves_full_complex_likelihood_at_irregular_times():
    t, a, b, va, vb, _ = scene()
    t = t-t.mean()+np.sin(np.arange(len(t)))*.2e-6
    raw = np.array([2000., 2000.+1/4.4e-6])
    p = np.array([.8, .2, .9, -.1, 34., -3., -4.])
    original = loss(p, t, a, b, va, vb, raw, 'common', prior=False)
    aligned = align_frame_phase_branch(raw, t, b, vb)
    # align_frame_phase_branch centers the rotation. Absorb the constant
    # gauge into the complex ratios when times have a nonzero mean.
    cycles = aligned['removed_frame_phase_cycles']
    ratios = (p[:4:2]+1j*p[1:4:2])*np.exp(-2j*np.pi*t.mean()*cycles*750)
    changed = p.copy()
    changed[:4] = np.column_stack((ratios.real, ratios.imag)).ravel()
    after = loss(changed, t, a, aligned['gain'], va, aligned['covariance'],
        aligned['native_delta_hz'], 'common', prior=False)
    np.testing.assert_allclose(after, original, atol=1e-7, rtol=1e-10)
    assert aligned['removed_frame_phase_cycles'][1] == 303


def test_joint_clock_recovers_injected_pilot_alias_with_fractional_frame_times():
    rng = np.random.default_rng(415)
    t = np.arange(36)/750+np.sin(np.arange(36))*.15e-6
    raw = np.array([2000., 2000.+1/4.4e-6])
    physical = 2034.
    a = np.exp(1j*rng.uniform(-np.pi, np.pi, (len(t), 2)))
    b = a*np.exp(2j*np.pi*t[:, None]*(physical-raw)[None])
    cov = np.tile(np.eye(2)*.005, (len(t), 1, 1))
    aligned = align_frame_phase_branch(raw, t, b, cov)
    train = np.arange(len(t)) % 2 == 0
    fitted = fit(t[train], a[train], aligned['gain'][train], cov[train],
        aligned['covariance'][train], aligned['native_delta_hz'])
    np.testing.assert_allclose(fitted['corrected_RX_delta_hz'], physical, atol=.2)
