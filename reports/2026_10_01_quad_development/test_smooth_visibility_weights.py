import numpy as np
import pytest
from smooth_visibility_weights import log_weights


def test_mass_and_all_branch_derivatives_including_background():
    margins=np.array([[.02,-.03],[.5,.1],[-.2,.4]])
    jac=np.array([[[1.,2.],[3.,-1.]],[[.5,1.],[2.,.2]],[[-1.,3.],[.7,-.1]]])
    logs,gradient=log_weights(margins,jac,.1,.8)
    np.testing.assert_allclose(np.exp(logs).sum(),1.,atol=1e-14)
    for index in range(2):
        h=1e-6
        plus=log_weights(margins+h*jac[:,:,index],jac,.1,.8)[0]
        minus=log_weights(margins-h*jac[:,:,index],jac,.1,.8)[0]
        np.testing.assert_allclose((plus-minus)/(2*h),gradient[:,index],rtol=1e-7,atol=1e-7)
    np.testing.assert_allclose(np.exp(logs)@gradient,np.zeros(2),atol=1e-13)
    assert np.linalg.norm(gradient[-1])>0


def test_extreme_margins_are_finite_and_approach_hard_gate_mass():
    logs,gradient=log_weights([[10000.,10000.],[-10000.,10000.]],np.ones((2,2,1)),.01,.8)
    assert np.all(np.isfinite(logs)) and np.all(np.isfinite(gradient))
    np.testing.assert_allclose(np.exp(logs),[.4,0.,.6],atol=1e-14)


@pytest.mark.parametrize('width,mass',[(0,.8),(-1,.8),(.1,1),(.1,0),(.1,float('nan'))])
def test_invalid_scale_or_mass_rejected(width,mass):
    with pytest.raises(ValueError):log_weights([[0]],np.ones((1,1,1)),width,mass)
