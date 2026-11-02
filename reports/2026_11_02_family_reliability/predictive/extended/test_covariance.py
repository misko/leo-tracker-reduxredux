"""Law-of-total-covariance audit against a fully joint linear Gaussian model."""
import numpy as np


def test_conditional_nuisance_plus_total_mean_position_has_no_double_count():
    rng=np.random.default_rng(203);n=17;m=8;k=4;d=2
    a=rng.normal(size=(n,k));b=rng.normal(size=(n,d));at=rng.normal(size=(m,k));bt=rng.normal(size=(m,d))
    noise=.7;position_prior=np.diag([2.,3.]);prior=np.zeros((k+d,k+d));prior[:k,:k]=np.eye(k);prior[k:,k:]=np.linalg.inv(position_prior)
    design=np.column_stack((a,b));joint=np.linalg.inv(prior+design.T@design/noise**2)
    nuisance=np.linalg.inv(np.eye(k)+a.T@a/noise**2)
    mean_derivative=bt-at@nuisance@a.T@b/noise**2
    marginal_x=joint[k:,k:]
    via_total=at@nuisance@at.T+mean_derivative@marginal_x@mean_derivative.T
    held_design=np.column_stack((at,bt));via_joint=held_design@joint@held_design.T
    assert np.allclose(via_total,via_joint,rtol=1e-10,atol=1e-10)


def test_inverse_half_minus_two_log_density_hessian_is_position_covariance():
    covariance=np.array([[2.,.3],[.3,1.]])
    precision=np.linalg.inv(covariance);hessian=2*precision
    assert np.allclose(np.linalg.inv(hessian/2),covariance)
