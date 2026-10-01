import numpy as np
import pytest
from marginal_window_objective import MarginalWindowObjective


class Port:
    def __init__(self,name,slopes):self.observation_ids=(name,);self.slopes=np.asarray(slopes)
    def score_all(self,x):return self.slopes@x
    def marginal_score_gradient(self,x):
        scores=self.score_all(x);weights=np.exp(scores-max(scores));p=weights/sum(weights)
        return float(max(scores)+np.log(sum(weights))),p@self.slopes
    def marginal_score(self,x):return self.marginal_score_gradient(x)[0]


def test_full_marginal_maps_priors_and_ignores_conditioning_labels():
    ports=[Port('a',[[1,2,3],[-2,1,0]]),Port('b',[[2,-1,4],[0,2,-3]])]
    model=MarginalWindowObjective(ports,[[0,1,2],[0,1,3]],[0,0,4,2])
    x=np.array([.2,-.3,.1,.4]);value,g,labels=model.evaluate(x)
    other=model.evaluate(x,tuple(1-i for i in labels))
    assert other[0]==value and other[2]==labels
    numeric=[]
    for i in range(4):
        d=np.eye(1,4,i)[0]*1e-5
        numeric.append((model.evaluate(x+d,gradient=False)[0]-model.evaluate(x-d,gradient=False)[0])/2e-5)
    np.testing.assert_allclose(g,numeric,atol=1e-8)
    with pytest.raises(ValueError):MarginalWindowObjective([ports[0],ports[0]],[[0,1,2],[0,1,3]],[0,0,4,2])
