"""Numerical-only tests; execute with the pinned SciPy scientific runtime."""
import numpy as np
from loose_nuisance_model import additional_prior,loosen_bounds,kkt_residual,polish_active_face


def test_doubled_prior_and_gradient():
    v=np.arange(12,dtype=float)/3;size=11
    old=.5*(v[6]/10)**2+.5*np.sum(v[7:size]**2)
    value,g=additional_prior(v,size)
    np.testing.assert_allclose(old+value,old/4,atol=1e-12)
    for i in range(len(v)):
        step=np.zeros_like(v);step[i]=1e-5
        numeric=(additional_prior(v+step,size)[0]-additional_prior(v-step,size)[0])/2e-5
        np.testing.assert_allclose(g[i],numeric,atol=1e-9)


def test_bounds_double_only_nuisance():
    original=[(-200,200)]*2+[(None,None),(-50,50),(None,None),(-50,50),(-10,10),
                                 (None,None),(-5000,5000)]
    expected=[(-200,200)]*2+[(None,None),(-100,100),(None,None),(-100,100),(-20,20),
                                 (None,None),(-10000,10000)]
    assert loosen_bounds(original)==expected
    assert original[3]==(-50,50)


def test_kkt_and_polish_without_individual_cap():
    A=np.zeros((0,3));bounds=[(3.,3.),(-100.,100.),(None,None)]
    def objective(v):
        error=v-np.array([3.,101.,4.]);return float(error@error),2*error
    result=polish_active_face(objective,np.array([3.,100.,3.99]),np.ones(3),bounds,A)
    np.testing.assert_allclose(result,[3.,100.,4.],atol=1e-9)
    assert kkt_residual(result,objective(result)[1],np.ones(3),bounds,A)<1e-8


if __name__=='__main__':
    test_doubled_prior_and_gradient()
    test_bounds_double_only_nuisance()
    test_kkt_and_polish_without_individual_cap()
    print('3 loose-nuisance tests passed')
