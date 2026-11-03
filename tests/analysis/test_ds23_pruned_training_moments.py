import numpy as np
from dsx01_hierarchical_bound import hierarchical_bound
from ds23_pruned_training_moments import pruned_moments


def test_pruned_training_preserves_observed_and_unobserved_prior_moments():
    r=np.random.default_rng(719);u=r.normal(size=(60,9));u[:,[2,4,8]]=0.
    y=r.normal(size=60);sigma=r.uniform(.5,2.,60);groups=np.repeat(np.arange(3),20);powers=np.array([.3,.7,1.])
    prior=np.array([-1,0,1,-1,2,-1,-1,-1,-1]);scale=np.r_[np.ones(7),.3,.3]
    expected=hierarchical_bound(y,u,sigma,groups,powers=powers,prior_groups=prior,prior_nu=5.)
    actual=pruned_moments(y,u,sigma,groups,powers,prior,5.,scale)
    np.testing.assert_allclose(actual['coefficient'],expected['coefficient']*scale,atol=1e-10)
    np.testing.assert_allclose(actual['coefficient_prior_precision'],expected['coefficient_prior_precision']/scale**2,atol=1e-10)
    np.testing.assert_allclose(actual['noise_precision'],expected['noise_precision'],atol=1e-10)
    assert actual['active_nuisance_columns']==6 and 'negative_twice_elbo' not in actual
