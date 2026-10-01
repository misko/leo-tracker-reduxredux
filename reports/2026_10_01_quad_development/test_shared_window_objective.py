import numpy as np
import pytest
from shared_window_objective import WindowObjective


class Port:
    def __init__(self,name,target):self.observation_ids=(name,);self.target=np.asarray(target)
    def score_all(self,x):return np.array([-.5*np.sum((x-self.target)**2),-100.])
    def score_selected(self,x,i):return self.score_all(x)[i]
    def score_gradient(self,x,i):return self.target-x if i==0 else np.zeros_like(x)


def test_shared_position_and_disjoint_nuisance_gradients_count_once():
    ports=[Port('a',[1,2,3]),Port('b',[-1,1,4])]
    model=WindowObjective(ports,[[0,1,2],[0,1,3]],[0,0,2,3])
    x=np.array([.1,.2,.3,.4]);value,g,labels=model.evaluate(x)
    assert labels==(0,0)
    for i in range(4):
        d=np.eye(4)[i]*1e-5
        finite=(model.evaluate(x+d,labels,False)[0]-model.evaluate(x-d,labels,False)[0])/2e-5
        np.testing.assert_allclose(finite,g[i],rtol=1e-8,atol=1e-8)
    with pytest.raises(ValueError,match='reused'):WindowObjective([ports[0],ports[0]],[[0,1,2],[0,1,3]],[0,0,2,3])
