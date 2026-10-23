import numpy as np
from ds23_joint_phase_alias_nomination import integrate,PERIOD


def test_phase_quadrature_preserves_a_phase_independent_gaussian_density():
    result=integrate([0.,0.],[0.,0.],np.eye(2),np.linspace(-8,8,1001),[0.],[1.],None,
        lambda phase:(np.zeros((1,2)),np.array([True])))
    assert abs(result['score'][0]-2*np.log(2*np.pi))<1e-10


def test_alias_is_allowed_to_change_with_phase_before_selecting_a_nominee():
    def geometry(phase):return np.array([[.49*PERIOD if phase==0 else PERIOD+10]]),np.array([True])
    result=integrate([10.],[0.],[[25.]],np.array([0.,1.]),[0.],[10.],None,geometry)
    assert result['peak_phase_s'][0]==1. and result['aliases'][0]==1
