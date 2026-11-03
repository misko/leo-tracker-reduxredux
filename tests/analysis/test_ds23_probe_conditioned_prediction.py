from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_probe_conditioned_prediction import symmetrized_RF_covariance,condition_rows


def test_equal_common_loading_has_positive_conditional_variance():
    r=symmetrized_RF_covariance(100.,100.,9900.)
    assert r['kappa']==.99
    assert r['conditional_sigma_hz']==pytest.approx(np.sqrt(199.))
    bounded=symmetrized_RF_covariance(100.,90.,12000.)
    assert 0<bounded['kappa']<1 and bounded['conditional_sigma_hz']>5


def test_conditional_transformation_is_exact_and_preserves_originals():
    y=np.array([3.,7.]);u=np.array([[1.,2.],[3.,4.]]);m=np.array([2.,6.])
    yy,uu,mm=condition_rows(y,u,m,[5.],[[7.,8.]],[4.],[1],[0],.5)
    np.testing.assert_array_equal(yy,[3.,4.5]);np.testing.assert_array_equal(uu,[[1.,2.],[-.5,0.]])
    np.testing.assert_array_equal(mm,[2.,4.]);np.testing.assert_array_equal(y,[3.,7.])
    np.testing.assert_array_equal(u,[[1.,2.],[3.,4.]])


def test_conditional_factor_does_not_double_count_primary_gaussian_measurement():
    variance=10000.;correlation=.98;k=correlation
    covariance=np.array([[variance,variance*k],[variance*k,variance]])
    y=np.array([47.,51.]);mean=np.array([3.,-2.]);residual=y-mean
    exact=residual@np.linalg.solve(covariance,residual)+np.linalg.slogdet(covariance)[1]
    conditional=(residual[0]**2/variance+np.log(variance)+
        (residual[1]-k*residual[0])**2/(variance*(1-k*k))+np.log(variance*(1-k*k)))
    assert conditional==pytest.approx(exact,abs=1e-12)


def test_duplicated_secondary_rows_are_rejected():
    with pytest.raises(ValueError,match='unique'):
        condition_rows([1.],[[1.]],[0.],[2.],[[2.]],[0.],[0,0],[0,0],.5)
