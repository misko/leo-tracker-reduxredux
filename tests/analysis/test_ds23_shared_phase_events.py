import numpy as np
from ds23_shared_phase_events import whiten,event_cost,qualify
from learn_ds23_causal_phase_forecast import distribution_cost


def test_exchangeable_whitening_has_exact_independent_null_and_permutation_symmetry():
    z=np.array([1.,2.,-3.,4.]);permutation=[2,0,3,1]
    np.testing.assert_array_equal(whiten(z,0.)[0],z)
    np.testing.assert_allclose(whiten(z,.2)[0][permutation],whiten(z[permutation],.2)[0])
    np.testing.assert_allclose(event_cost(z,0.,3.),distribution_cost(z,np.ones(4),1.,3.).sum())


def test_whitening_matches_declared_covariance_and_density_jacobian():
    n=4;rho=.2;matrix=(1-rho)*np.eye(n)+rho*np.ones((n,n))
    w=np.column_stack([whiten(v,rho)[0] for v in np.eye(n)])
    np.testing.assert_allclose(w@matrix@w.T,np.eye(n),atol=1e-15)
    np.testing.assert_allclose(whiten(np.ones(n),rho)[1],np.linalg.slogdet(matrix)[1])


def test_few_publication_events_fail_closed():
    model=dict(shrinkage=0.,multiplier=1.,nu=3.)
    assert not qualify({},10,model,model)["qualified"]
