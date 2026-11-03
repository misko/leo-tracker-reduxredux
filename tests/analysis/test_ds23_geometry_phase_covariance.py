import numpy as np
import pytest
from scipy.stats import multivariate_normal, multivariate_t

from ds23_geometry_phase_covariance import (
    independent_cost, joint_cost, make_events, orbital_features, qualify,
    quadratic_logdet,
)


@pytest.mark.parametrize('nu', [None, 3., 8.])
def test_low_rank_normalized_density_matches_independent_dense_oracle(nu):
    rng = np.random.default_rng(817)
    features = rng.normal(size=(11, 4))
    features /= np.linalg.norm(features, axis=1)[:, None]
    z = rng.normal(size=11)
    rho = .6
    matrix = (1-rho)*np.eye(len(z))+rho*(features@features.T)
    quadratic, logdet = quadratic_logdet(z, features, rho)
    assert quadratic == pytest.approx(z@np.linalg.solve(matrix, z), abs=1e-11)
    assert logdet == pytest.approx(np.linalg.slogdet(matrix)[1], abs=1e-11)
    reference = (multivariate_normal.logpdf(z, cov=matrix) if nu is None else
                 multivariate_t.logpdf(z, shape=matrix*(nu-2)/nu, df=nu))
    assert joint_cost(z, features, rho, nu) == pytest.approx(-2*reference, abs=1e-10)


def test_preserves_univariate_student_marginal_and_distinguishes_shared_gamma_control():
    for nu in [None, 3., 8.]:
        for z in [-10., 0., 1.2]:
            for rho in [0., .6]:
                assert joint_cost([z], [[1.]], rho, nu) == pytest.approx(independent_cost([z], nu), abs=1e-12)
    z = np.array([.1, 4., -.2])
    assert joint_cost(z, np.ones((3, 1)), 0., 3.) != pytest.approx(independent_cost(z, 3.))
    assert joint_cost(z, np.ones((3, 1)), 0., None) == pytest.approx(independent_cost(z, None))


def test_geometry_allows_negative_covariance_and_is_invariant_to_global_rotation_and_order():
    a = orbital_features([7000., 0., 0.], [0., 7., 0.])
    b = orbital_features([-7000., 0., 0.], [0., -7., 0.])
    assert a['radial_velocity']@b['radial_velocity'] == pytest.approx(-1.)
    assert a['normal']@b['normal'] == pytest.approx(1.)
    features = np.array([a['radial_velocity'], b['radial_velocity']])
    z = np.array([2., -1.])
    np.testing.assert_allclose(joint_cost(z, features, .6, 3.), joint_cost(z[::-1], features[::-1], .6, 3.))
    angle = .7
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    c = orbital_features(rotation@np.array([7000., 0., 0.]), rotation@np.array([0., 7., 0.]))
    d = orbital_features(rotation@np.array([-7000., 0., 0.]), rotation@np.array([0., -7., 0.]))
    assert joint_cost(z, features, .6, 3.) == pytest.approx(joint_cost(z, [c['radial_velocity'], d['radial_velocity']], .6, 3.))


def test_invalid_covariance_inputs_fail_closed():
    with pytest.raises(ValueError):
        joint_cost([1., 2.], [[1.], [2.]], .1, 3.)
    with pytest.raises(ValueError):
        joint_cost([1.], [[1.]], 1., 3.)
    with pytest.raises(ValueError):
        joint_cost([1.], [[1.]], .1, 2.)
    with pytest.raises(ValueError):
        orbital_features([1., 0., 0.], [1., 0., 0.])


def test_sparse_events_and_duplicate_innovations_do_not_qualify():
    model = dict(shrinkage=0., multiplier=1., nu=3.)
    assert not qualify([], 10, model, {})['qualified']
    row = dict(norad=1, validation_time_ns=1, predicted_sigma_s=1., age_s=1.,
               unit_forecast_s=0., next_innovation_s=0., forecast_publication_ns=0,
               normal=[1., 0., 0.], radial_velocity=[1., 0., 0., 0., 0., 0.])
    with pytest.raises(ValueError, match='one innovation'):
        make_events([row, row], model, {})


def test_detects_injected_signed_geometry_and_future_labels_cannot_change_training():
    rng = np.random.default_rng(991)
    count = 100
    normal = rng.normal(size=(count, 3))
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    rv = rng.normal(size=(count, 6))
    rv /= np.linalg.norm(rv, axis=1)[:, None]
    rows = []
    for t in range(16):
        z = (np.sqrt(.2)*rng.normal(size=count)+np.sqrt(.8)*(normal@rng.normal(size=3)))
        z /= np.sqrt(rng.gamma(1.5, 2.))
        for k in range(count):
            rows.append(dict(norad=k+1, validation_time_ns=t+10,
                             forecast_publication_ns=t+8 if k % 2 else t+9,
                             predicted_sigma_s=1., age_s=43200., unit_forecast_s=0.,
                             next_innovation_s=float(z[k]), normal=normal[k], radial_velocity=rv[k]))
    model = dict(shrinkage=0., multiplier=1., nu=3.)
    result = qualify(rows, 19, model, {})
    assert result['qualified']
    assert result['selected_kind'] == 'normal'
    assert result['selected_rho'] == .8
    changed = [dict(r, next_innovation_s=r['next_innovation_s']+100)
               if r['validation_time_ns'] > 19 or r['norad'] % 5 == 0 else r for r in rows]
    perturbed = qualify(changed, 19, model, {})
    assert perturbed['prefix_model'] == result['prefix_model']
    assert perturbed['prefix_location'] == result['prefix_location']
    assert perturbed['prefix_selection'] == result['prefix_selection']
    assert perturbed['controls'] == result['controls']
