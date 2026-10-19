import numpy as np
from ds23_correlated_family_screen import screen
from ds23_family_screen import screen_family
from dsx01_joint_marginal import integrated_gaussian


def fixture():
    rng = np.random.default_rng(71)
    curves = []
    for n in (9, 13):
        curves.append(dict(observed=rng.normal(size=n)*40, predicted=rng.normal(size=(3, n))*70,
            derivative=rng.normal(size=(3, n))*8, sigma=np.linspace(10, 20, n), power=.7, visible=np.ones(3, bool)))
    return curves


def test_independent_covariance_reproduces_existing_common_phase_screen():
    curves, widths = fixture(), np.array([1., 2., 3.])
    old = screen_family(curves, widths)
    new = screen(curves, widths, np.eye(2)*300**2)
    for key in ('cost', 'phase_correction_s', 'bias_hz', 'aliases'):
        np.testing.assert_allclose(new[key], old[key], rtol=1e-9, atol=1e-7)


def test_correlated_screen_matches_explicit_full_gaussian_integration():
    curves, widths = fixture(), np.array([1., 2., 3.])
    covariance = np.array([[90000., 81000.], [81000., 110000.]])
    root = np.linalg.cholesky(covariance)
    actual = screen(curves, widths, covariance)
    for candidate in range(3):
        values, designs, noise = [], [], []
        for k, c in enumerate(curves):
            values.extend(c['observed'] + actual['aliases'][k][candidate]*(1/4.4e-6) - c['predicted'][candidate])
            designs.extend(np.column_stack((c['derivative'][candidate]*widths[candidate], np.broadcast_to(root[k], (len(c['observed']), 2)))))
            noise.extend(c['sigma']/np.sqrt(c['power']))
        result = integrated_gaussian(values, designs, noise)
        np.testing.assert_allclose(actual['cost'][candidate], result['quadratic']+result['logvolume'], rtol=1e-9)


def test_shared_carrier_favors_common_offsets_and_visibility_is_enforced():
    curve = dict(predicted=np.zeros((1, 8)), derivative=np.zeros((1, 8)), sigma=np.full(8, 10.), power=1., visible=[True])
    same = [dict(curve, observed=np.full(8, v)) for v in (300., 300.)]
    opposite = [dict(curve, observed=np.full(8, v)) for v in (300., -300.)]
    covariance = np.eye(2)*30**2 + 300**2*np.ones((2, 2))
    assert screen(opposite, [1.], covariance)['cost'][0] > screen(same, [1.], covariance)['cost'][0] + 100
    same[0]['visible'] = [False]
    assert np.isinf(screen(same, [1.], covariance)['cost'][0])
