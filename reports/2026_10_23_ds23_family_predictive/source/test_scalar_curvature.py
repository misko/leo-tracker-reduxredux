import numpy as np
from scalar_curvature import differences


def test_exact_quadratic_recovers_cross_term_and_newton_step():
    h=np.array([[2.,.3],[.3,5.]])
    center=np.array([.4,-.7]);x=np.array([2.,3.])
    r=differences(lambda z:float((z-center)@h@(z-center)/2),x,.05)
    assert np.allclose(r['hessian'],h)
    assert np.allclose(x+r['local_newton_step_km'],center)


def test_saddle_is_not_given_positive_curvature_uncertainty():
    r=differences(lambda z:z[0]**2-z[1]**2,np.zeros(2),.02)
    assert r['condition_number'] is None and r['local_newton_step_km'] is None
