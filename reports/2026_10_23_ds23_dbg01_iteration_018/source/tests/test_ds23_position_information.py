from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_position_information import marginal_position_information


def test_projection_matches_dense_covariance_marginal_information():
    rng=np.random.default_rng(1010);j=rng.normal(size=(30,2));u=rng.normal(size=(30,7));w=rng.uniform(.2,2.,30);prior=rng.uniform(.5,3.,7)
    covariance=np.diag(1/w)+(u/prior)@u.T
    direct=j.T@np.linalg.solve(covariance,j)
    np.testing.assert_allclose(marginal_position_information(j,u,w,prior),direct,rtol=1e-12,atol=1e-12)


def test_many_precise_points_cannot_remove_a_degenerate_phase_prior():
    n=100;sigma=.01;phase_sigma=2.
    j=np.column_stack((np.ones(n),np.linspace(-1,1,n)));u=np.ones((n,1));w=np.full(n,1/sigma**2)
    information=marginal_position_information(j,u,w,np.array([1/phase_sigma**2]))
    assert information[0,0]==pytest.approx(n/(sigma**2+n*phase_sigma**2),rel=1e-9)
    assert information[0,0]<.251
    assert j[:,0]@(w*j[:,0])>999999


def test_adding_measurements_increases_marginal_information_without_reusing_priors():
    rng=np.random.default_rng(2020);j=rng.normal(size=(50,2));u=rng.normal(size=(50,8));w=np.ones(50);prior=np.ones(8)
    before=marginal_position_information(j[:30],u[:30],w[:30],prior)
    after=marginal_position_information(j,u,w,prior)
    assert np.linalg.eigvalsh(after-before).min()>0
