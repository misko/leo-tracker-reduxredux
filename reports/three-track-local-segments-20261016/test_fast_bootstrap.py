import unittest
import numpy as np
from types import SimpleNamespace

from fast_bootstrap import bootstrap_position,shape_statistics
from leo.analysis.regional_position_bootstrap import bootstrap_position as oracle
from leo.contracts.regional_position import PositionObservations


class Bank:
    def __init__(self,numbers):self.numbers=np.array(numbers)
    def select(self,ix):return Bank(self.numbers[ix])


def predict(bank,obs,prior,point,shifts,derivatives=False):
    t=obs.times_s[:,None]+shifts[None,:]
    n=bank.numbers[None,:]
    prediction=.03*n*t*t+2*n*t+100*n
    return prediction,np.ones_like(prediction,dtype=bool),None,None


class BootstrapTests(unittest.TestCase):
    def test_batched_statistics_match_original_independent_stopping(self):
        rng=np.random.default_rng(80);residual=rng.normal(10000,700,(7,6,9))
        residual[0,:,0]=rng.normal(3,1,6);visible=rng.random(residual.shape)>.02
        cost,rms=shape_statistics(residual,visible)
        for i,r in enumerate(residual):
            location=np.median(r,axis=0)
            for _ in range(10):
                weights=1/np.sqrt(1+((r-location)/200)**2);updated=np.sum(weights*r,axis=0)/weights.sum(axis=0)
                if max(abs(updated-location))<.01:break
                location=updated
            centered=r-location;reference=np.mean(2*200**2*(np.sqrt(1+(centered/200)**2)-1),axis=0)
            reference[np.mean(visible[i],axis=0)<.9]=np.inf
            np.testing.assert_allclose(cost[i],reference,rtol=0,atol=1e-9)
            np.testing.assert_allclose(rms[i],np.sqrt(np.mean(centered**2,axis=0)),rtol=0,atol=1e-9)

    def test_complete_bootstrap_matches_oracle_with_varied_length_tracks(self):
        lengths=[9,11,7,5];t=np.concatenate([np.linspace(j*25,j*25+15,n) for j,n in enumerate(lengths)])
        rx=np.concatenate([np.full(n,j%2) for j,n in enumerate(lengths)])
        k=np.concatenate([np.full(n,[7,3,7,3][j]) for j,n in enumerate(lengths)])
        y=.03*k*t*t+2*k*t+100*k+np.where(rx==0,12000.,-8000.)+3*t
        obs=PositionObservations(tuple(map(str,range(len(t)))),t,y,np.full(len(t),11e9),rx,np.ones(len(t)),np.ones(len(t)))
        edges=np.r_[0,np.cumsum(lengths)];tracks=[tuple(range(a,b)) for a,b in zip(edges[:-1],edges[1:])]
        bank=Bank([7,3,12]);kwargs=dict(maximum_seconds=5.,samples_per_track=6,orbit_predictor=predict)
        old=oracle(obs,bank,None,[0,0],tracks,**kwargs);new=bootstrap_position(obs,bank,None,[0,0],tracks,**kwargs)
        self.assertEqual(old.satellite_indices,new.satellite_indices)
        self.assertEqual([(m.satellite_index,m.timing_s) for m in old.matches],[(m.satellite_index,m.timing_s) for m in new.matches])
        np.testing.assert_allclose(new.vector,old.vector,rtol=0,atol=1e-8)
        np.testing.assert_allclose([m.shape_cost for m in new.matches],[m.shape_cost for m in old.matches],rtol=0,atol=1e-8)


if __name__=='__main__':unittest.main()
