from types import SimpleNamespace

import numpy as np
import pytest

import polish_position_score_sweep as polish


@pytest.mark.parametrize('target_x,expected_x',[(1.,1.),(5.,4.)])
def test_slsqp_respects_four_km_disk_and_original_constraints(monkeypatch,target_x,expected_x):
    monkeypatch.setattr(polish,'coordinate',lambda p:np.asarray(p))
    monkeypatch.setattr(polish,'coordinate_jacobian',lambda p:np.eye(2))
    target=np.zeros(9);target[0]=target_x;target[6]=.5
    def evaluate(v):
        return float(.5*np.sum((v-target)**2)),v-target
    base=SimpleNamespace(satellites=np.array([0,1]),basis=np.array([[1.],[-1.]])/np.sqrt(2),
        minimum_shift_s=-20.,maximum_shift_s=20.,state=lambda v:{'parameters':v})
    obj=SimpleNamespace(scale=np.ones(9),size=8,base=base,evaluate=evaluate,
        bounds=[(-200,200),(-200,200),(None,None),(-50,50),(None,None),(-50,50),(-10,10),(None,None),(0,0)])
    result=polish.slsqp_fit(obj,dict(vector=np.zeros(9),point_km=[0.,0.]),5.)
    np.testing.assert_allclose(result['point_km'],[expected_x,0.],atol=1e-6)
    assert result['success'] and result['kkt_residual']<=1e-3
    assert result['coefficient']==0.
    assert abs(result['vector'][6])<=10.


def test_invalid_budget_rejected():
    with pytest.raises(ValueError):polish.slsqp_fit(None,None,0.)
