"""Numerical-only tests; SciPy tests require the pinned scientific runtime."""
import numpy as np
from tight_timing_model import project_deviations,additional_prior,kkt_residual,polish_active_face
from timing_model import zero_sum_basis


def test_physical_deviation_projection_is_zero_sum_and_bounded():
    rng=np.random.default_rng(13)
    for n in (1,2,3,13):
        d=project_deviations(rng.normal(size=n)*5)
        assert abs(sum(d))<1e-12
        assert max(abs(d))<=.5
        B=zero_sum_basis(n);np.testing.assert_allclose(B@(B.T@d),d,atol=1e-12)
    np.testing.assert_allclose(project_deviations([-.2,.1,.1]),[-.2,.1,.1],atol=1e-12)


def test_gaussian_prior_difference_and_gradient():
    v=np.arange(11,dtype=float)/10;size=10
    value,g=additional_prior(v,size)
    old=.5*(v[6]/10)**2+.5*sum(v[7:size]**2)
    new=.5*v[6]**2+.5*sum((v[7:size]/.5)**2)
    np.testing.assert_allclose(value,new-old)
    for i in range(len(v)):
        step=np.zeros_like(v);step[i]=1e-6
        numerical=(additional_prior(v+step,size)[0]-additional_prior(v-step,size)[0])/2e-6
        np.testing.assert_allclose(g[i],numerical,atol=1e-8)


def test_kkt_handles_active_physical_timing_constraints():
    # A zero-sum pair hits +/-0.5: the nonzero raw gradient can satisfy KKT.
    B=zero_sum_basis(2);A=B.copy();v=np.array([np.sqrt(.5)])
    assert kkt_residual(v,np.array([-3.]),np.ones(1),[(None,None)],A)<1e-10
    assert kkt_residual(v,np.array([3.]),np.ones(1),[(None,None)],A)>2.9


def test_polish_respects_active_deviation_bound_and_fixed_coordinate():
    A=np.array([[0.,0.,1.],[0.,0.,-1.]])
    bounds=[(3.,3.),(None,None),(None,None)]
    def objective(v):
        error=v-np.array([3.,2.,1.]);return float(error@error),2*error
    result=polish_active_face(objective,np.array([3.,2.01,.5]),np.ones(3),bounds,A)
    np.testing.assert_allclose(result,[3.,2.,.5],atol=1e-9)
    assert kkt_residual(result,objective(result)[1],np.ones(3),bounds,A)<1e-8


if __name__=='__main__':
    test_physical_deviation_projection_is_zero_sum_and_bounded()
    test_gaussian_prior_difference_and_gradient()
    test_kkt_handles_active_physical_timing_constraints()
    test_polish_respects_active_deviation_bound_and_fixed_coordinate()
    print('4 constrained-timing tests passed')
