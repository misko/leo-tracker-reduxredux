import numpy as np
import pytest
from scan_discrepancy_quadratic import solve_discrepancy


def fixture():
    return np.array([[[5.,1.],[1.,2.]],[[1.,-.2],[-.2,3.]],[[2.,.3],[.3,1.]]]), np.array([[1.,-2.],[-3.,.5],[2.,1.5]])


def test_matches_full_joint_block_system():
    h,g=fixture()
    for sigma in (.01,.3,1.,10.):
        n=len(h); matrix=np.zeros((2+2*n,2+2*n)); rhs=np.zeros(2+2*n)
        matrix[:2,:2]=h.sum(axis=0);rhs[:2]=-g.sum(axis=0)
        for j in range(n):
            idx=slice(2+2*j,4+2*j)
            matrix[:2,idx]=matrix[idx,:2]=h[j]
            matrix[idx,idx]=h[j]+np.eye(2)/sigma**2;rhs[idx]=-g[j]
        direct=np.linalg.solve(matrix,rhs)
        result=solve_discrepancy(h,g,sigma)
        np.testing.assert_allclose(result['center'],direct[:2],atol=1e-11)
        np.testing.assert_allclose(result['offsets'].ravel(),direct[2:],atol=1e-11)
        np.testing.assert_allclose(result['offsets'].sum(axis=0),0,atol=1e-12)


def test_zero_single_and_large_scale_limits():
    h,g=fixture()
    zero=solve_discrepancy(h,g,0.)
    np.testing.assert_allclose(zero['center'],-np.linalg.solve(h.sum(axis=0),g.sum(axis=0)),atol=1e-14)
    np.testing.assert_array_equal(zero['offsets'],np.zeros((3,2)))
    for sigma in (0.,1.,100.):
        one=solve_discrepancy(h[:1],g[:1],sigma)
        np.testing.assert_allclose(one['center'],-np.linalg.solve(h[0],g[0]),atol=1e-12)
        np.testing.assert_allclose(one['offsets'],0,atol=1e-12)
    large=solve_discrepancy(h,g,1e4)
    np.testing.assert_allclose(large['center'],large['local_minima'].mean(axis=0),atol=1e-8)
    np.testing.assert_allclose(large['information']*1e8,len(h)*np.eye(2),atol=1e-7)


def test_information_weakens_and_translation_is_not_identified_by_scatter():
    h,g=fixture()
    a=solve_discrepancy(h,g,0.);b=solve_discrepancy(h,g,1.)
    assert np.min(np.linalg.eigvalsh(a['information']-b['information']))>0
    shift=np.array([3.,-7.])
    shifted=solve_discrepancy(h,g-np.einsum('nij,j->ni',h,shift),1.)
    np.testing.assert_allclose(shifted['center'],b['center']+shift)
    np.testing.assert_allclose(shifted['offsets'],b['offsets'],atol=1e-12)
    # Free common bias and common position have identical columns: exact gauge.
    combined=np.block([[h.sum(axis=0),h.sum(axis=0)],[h.sum(axis=0),h.sum(axis=0)]])
    np.testing.assert_allclose(combined@np.r_[shift,-shift],0,atol=1e-12)


def test_invalid_inputs():
    h,g=fixture()
    for hh,gg,s in ((h,g,-1),(h,g,float('nan')),(h*0,g,1),(h,g[:1],1),(h[:0],g[:0],1)):
        with pytest.raises(ValueError):solve_discrepancy(hh,gg,s)
