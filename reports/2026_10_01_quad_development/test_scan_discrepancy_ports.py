import numpy as np
import pytest
from leo.analysis.gaussian_sum_location import Prediction
from scan_discrepancy_ports import DiscrepancyPort, augment_window


class Port:
    dimension=4
    observation_ids=('a','b')
    observation=np.array([1.,2.])
    candidate_count=1
    priors_piecewise_constant=True
    def predict_selected(self,x,index):
        assert index==0
        return Prediction(np.array([x[0]**2+x[2],np.sin(x[1])+x[3]]),
            np.array([[2*x[0],0,1,0],[0,np.cos(x[1]),0,1]]),np.eye(2),True)
    def score_selected(self,x,index):
        if index==1:return -20.
        r=self.observation-self.predict_selected(x,index).mean
        return float(-r@r/2)
    def score_all(self,x):return np.array([self.score_selected(x,0),-20.])


def test_zero_parity_and_nonzero_chain_rule_without_mutation():
    base=Port();p=DiscrepancyPort(base,6,8)
    x=np.array([.3,.4,.1,-.1,0.,0.,0.,0.])
    np.testing.assert_array_equal(p.score_all(x),base.score_all(x[:4]))
    x[6:]=[.2,-.3];saved=x.copy();pred=p.predict_selected(x,0)
    for k in range(len(x)):
        d=np.eye(len(x))[k]*1e-6
        fd=(p.predict_selected(x+d,0).mean-p.predict_selected(x-d,0).mean)/2e-6
        np.testing.assert_allclose(fd,pred.jacobian[:,k],atol=1e-9)
    np.testing.assert_array_equal(x,saved)
    np.testing.assert_array_equal(pred.jacobian[:,4:6],0)
    assert p.score_selected(x,1)==-20 and p.observation_ids==base.observation_ids


def test_scan_isolation_and_precision():
    base=Port();prepared=({},[(None,None,[base]),(None,None,[base])],[],np.array([0.,0.,1.,4.]),[base,base])
    precision,ports=augment_window(prepared,.5)
    np.testing.assert_array_equal(precision,[0,0,1,4,4,4,4,4])
    x=np.zeros(8);x[4]=1.
    assert ports[0].score_selected(x,0)!=ports[1].score_selected(x,0)
    np.testing.assert_array_equal(ports[1].score_all(x),base.score_all(np.zeros(4)))


def test_invalid_layout_state_and_width():
    for offset,dim in ((3,8),(7,8),(4,5)):
        with pytest.raises(ValueError):DiscrepancyPort(Port(),offset,dim)
    p=DiscrepancyPort(Port(),4,6)
    for x in (np.zeros(5),np.full(6,np.nan)):
        with pytest.raises(ValueError):p.score_all(x)
    for s in (0,-1,float('nan')):
        with pytest.raises(ValueError):augment_window(None,s)
