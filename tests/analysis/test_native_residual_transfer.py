import numpy as np
from probe_native_residual_transfer import conditional_shift


def test_target_marginal_matches_augmented_gaussian_conditioning():
    rng=np.random.default_rng(12);h=rng.normal(size=(9,3));raw=rng.normal(size=9);gram=np.diag([2.,3.,4.]);sigma=np.linspace(.8,1.2,9);bias=.7
    r=conditional_shift(raw,h,gram,sigma,bias)
    design=np.column_stack([h,np.ones(9)]);prior=np.zeros((4,4));prior[:3,:3]=gram;prior[3,3]=1/bias**2
    posterior=np.linalg.solve(prior+design.T@(design/sigma[:,None]**2),design.T@(raw/sigma**2))
    np.testing.assert_allclose(r['shift'],posterior[:3]);np.testing.assert_allclose(r['bias_hz'],posterior[3])
    c=h@np.linalg.solve(gram,h.T)+np.diag(sigma**2)+bias**2
    np.testing.assert_allclose(r['quadratic'],raw@np.linalg.solve(c,raw));np.testing.assert_allclose(r['logdet'],np.linalg.slogdet(c)[1])
