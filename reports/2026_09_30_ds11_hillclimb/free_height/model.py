"""Original candidate mixture with receiver ellipsoidal height as a parameter."""
from pathlib import Path
import sys
import numpy as np
from scipy.special import logsumexp
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
import ds7_fast_baseline_adapter as fast
STEPS=np.array([1e-4,1e-4,1e-5,1e-4])
class Geometry(fast.Stationary):
    def prediction(self,track,x):
        receiver,up=fast.baseline.site(*self.coordinates(x));receiver=receiver+x[3]*up
        hi=min(max(int(np.searchsorted(self.taus,x[2],side='right')),1),len(self.taus)-1);lo=hi-1
        w=(x[2]-self.taus[lo])/(self.taus[hi]-self.taus[lo])
        pos=track['candidate_position_km'][:,lo]*(1-w)+track['candidate_position_km'][:,hi]*w
        vel=track['candidate_velocity_km_s'][:,lo]*(1-w)+track['candidate_velocity_km_s'][:,hi]*w
        unit=pos-receiver;unit/=np.linalg.norm(unit,axis=-1)[...,None]
        return -fast.REFERENCE_RF_HZ/fast.baseline.LIGHT_KM_S*np.sum(unit*vel,axis=-1),np.any((unit@up)[:,track['mask']]>=0,axis=1)

class Model:
    def __init__(self,doc,config,geometry_factory=Geometry):
        self.doc=doc;self.model=geometry_factory(doc,config)
    def evaluate(self,x,gradient=True):
        x=np.asarray(x,dtype=float);score=0.;derivative=np.zeros(4);held=0.
        for t in self.doc['tracks']:
            pred,visible=self.model.prediction(t,x);residual=t['y'][None,:]-pred
            train,joint,audits,offsets=fast.profile(residual,t['mask'])
            assert all(a['converged'] for a in audits)
            train=np.where(visible,train,-np.inf);joint=np.where(visible,joint,-np.inf)
            normal=logsumexp(train);score+=float(normal-np.log(t['catalogue_size']))
            held+=float(logsumexp(joint)-normal)
            if gradient:
                centered=residual[:,t['mask']]-offsets[:,None]
                slope=5*centered/(40000+centered**2);posterior=np.exp(train-normal)
                for axis,step in enumerate(STEPS):
                    d=np.eye(4)[axis]*step
                    jac=(self.model.prediction(t,x+d)[0]-self.model.prediction(t,x-d)[0])/(2*step)
                    derivative[axis]+=float(posterior@np.sum(slope*jac[:,t['mask']],axis=1))
        return dict(score=score,gradient=derivative,held=held)
