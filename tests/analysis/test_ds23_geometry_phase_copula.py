import numpy as np
import pytest
from scipy.stats import multivariate_normal, norm, t

from ds23_geometry_phase_copula import joint_cost, normal_scores, qualify
from ds23_geometry_phase_covariance import independent_cost, qualify as qualify_elliptical


@pytest.mark.parametrize('nu', [None, 3., 8.])
def test_copula_density_matches_dense_probability_integral_transform(nu):
    z = np.array([-8., -.2, 0., 1.2, 15.])
    f = np.array([[1., 0.], [.8, .6], [0., -1.], [-1., 0.], [.6, -.8]])
    rho = .6
    matrix = (1-rho)*np.eye(5)+rho*(f@f.T)
    scale = None if nu is None else np.sqrt((nu-2)/nu)
    w = z if nu is None else np.where(z < 0, norm.ppf(t.cdf(z/scale, nu)),
                                     norm.isf(t.sf(z/scale, nu)))
    np.testing.assert_allclose(normal_scores(z, nu), w, atol=2e-12, rtol=2e-12)
    adjustment = multivariate_normal.logpdf(w, cov=matrix)-norm.logpdf(w).sum()
    expected = independent_cost(z, nu)-2*adjustment
    assert joint_cost(z, f, rho, nu) == pytest.approx(expected, abs=1e-10)
    assert joint_cost(z, f, 0., nu) == pytest.approx(independent_cost(z, nu), abs=1e-12)


def test_exact_univariate_marginal_and_symmetric_extreme_tail_transform():
    for nu in [3., 8.]:
        for z in [-1e8, -1., 0., 10., 1e8]:
            assert np.isfinite(normal_scores([z], nu)).all()
            assert normal_scores([z], nu)[0] == -normal_scores([-z], nu)[0]
            assert joint_cost([z], [[1.]], .8, nu) == pytest.approx(independent_cost([z], nu), abs=1e-10)
    with pytest.raises(ValueError):
        normal_scores([np.nan], 3.)
    with pytest.raises(ValueError):
        normal_scores([1.], 2.)


def test_injected_copula_qualifies_and_held_labels_do_not_change_prefix_fits():
    rng = np.random.default_rng(991)
    count = 100
    normal = rng.normal(size=(count, 3))
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    rv = rng.normal(size=(count, 6))
    rv /= np.linalg.norm(rv, axis=1)[:, None]
    rows = []
    for stamp in range(16):
        w = np.sqrt(.2)*rng.normal(size=count)+np.sqrt(.8)*(normal@rng.normal(size=3))
        z = t.ppf(norm.cdf(w), 3)/np.sqrt(3)
        for k in range(count):
            rows.append(dict(norad=k+1, validation_time_ns=stamp+10, forecast_publication_ns=stamp+9,
                             predicted_sigma_s=1., age_s=43200., unit_forecast_s=0.,
                             next_innovation_s=float(z[k]), normal=normal[k], radial_velocity=rv[k]))
    model = dict(shrinkage=0., multiplier=1., nu=3.)
    earlier = qualify_elliptical(rows, 19, model, {})
    result = qualify(rows, 19, earlier, model, {})
    assert result['qualified'] and result['selected_kind'] == 'normal' and result['selected_rho'] == .8
    changed = [dict(r, next_innovation_s=r['next_innovation_s']+100)
               if r['validation_time_ns'] > 19 or r['norad'] % 5 == 0 else r for r in rows]
    perturbed = qualify(changed, 19, earlier, model, {})
    assert perturbed['prefix_selection'] == result['prefix_selection']
    assert perturbed['global_control'] == result['global_control']
    assert perturbed['publication_control'] == result['publication_control']
