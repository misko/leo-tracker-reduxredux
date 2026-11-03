"""Schur position information matches the directly marginalized covariance."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from diagnose_ds23_position_information import marginal_information


def test_schur_information_matches_dense_marginalization():
    rng=np.random.default_rng(41);d=rng.normal(size=(8,2));u=rng.normal(size=(8,3))
    w=np.linspace(.3,2.,8);p=np.array([1.,2.,3.])
    covariance=np.diag(1/w)+(u/p)@u.T
    direct=d.T@np.linalg.solve(covariance,d)
    result=marginal_information(d,u,w,p)
    assert result['information']==pytest.approx(direct)
    assert result['covariance_km2']==pytest.approx(np.linalg.inv(direct))


def test_freezing_nuisance_variables_cannot_reduce_information():
    d=np.array([[1.,0.],[0.,1.],[1.,1.]]);u=d.copy();w=np.ones(3)
    free=marginal_information(d,u,w,np.ones(2))
    fixed=marginal_information(d,np.empty((3,0)),w,np.empty(0))
    assert min(np.linalg.eigvalsh(fixed['information']-free['information']))>=-1e-12
    assert free['RMS_radius_km']>fixed['RMS_radius_km']


def test_rank_deficient_geometry_is_not_reported_as_a_finite_error_bound():
    d=np.ones((3,2))
    assert not marginal_information(d,np.empty((3,0)),np.ones(3),np.empty(0))['positive_definite']
