import numpy as np
from local_math import bias_basis,position_response,susceptibility,quantile_indices


def test_response_matches_joint_dense_normal_equations():
    rng=np.random.default_rng(1742);j=rng.normal(size=(20,2));u=rng.normal(size=(20,4));w=np.linspace(.1,2,20)
    prior=np.diag([1.,2.,3.,4.]);g=prior+u.T@(w[:,None]*u);cross=u.T@(w[:,None]*j)
    information=j.T@(w[:,None]*j)-cross.T@np.linalg.solve(g,cross)
    h,error=position_response(j,u,w,g,cross,information)
    joint=np.block([[j.T@(w[:,None]*j),cross.T],[cross,g]])
    expected=np.linalg.solve(joint,np.vstack((j.T*w,u.T*w)))[:2]
    assert np.max(abs(h-expected))<1e-12 and error<1e-12


def test_unit_RMS_and_RF_scaling():
    t=np.linspace(0,10,21);b=bias_basis(t,np.ones(21))
    assert np.allclose(b.T@b/21,np.eye(3))
    assert np.allclose(bias_basis(t,np.full(21,2.)),2*b)


def test_permutation_basis_invariant_susceptibility():
    rng=np.random.default_rng(1);h=rng.normal(size=(2,21));t=np.linspace(2,9,21);q=np.linspace(.9,1.1,21)
    weak=np.array([.6,.8]);a,_,_=susceptibility(h,weak,np.arange(21),t,q)
    order=rng.permutation(21);b,_,_=susceptibility(h[:,order],weak,np.arange(21),t[order],q[order])
    assert abs(a-b)<1e-12


def test_fixed_time_quantiles():
    assert quantile_indices(21)==[5,15]
    assert quantile_indices(20)==[5,14]
