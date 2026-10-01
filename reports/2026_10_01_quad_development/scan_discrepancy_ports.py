"""Research-only apparent scan position x+b_j over unchanged window ports."""
from dataclasses import dataclass
import numpy as np
from leo.analysis.gaussian_sum_location import Prediction


@dataclass(frozen=True)
class DiscrepancyPort:
    baseline: object
    offset_start: int
    dimension: int

    def __post_init__(self):
        base = self.baseline.dimension
        if (not isinstance(self.offset_start, int) or not isinstance(self.dimension, int)
                or self.offset_start < base or self.offset_start+2 > self.dimension):
            raise ValueError('Invalid discrepancy columns')

    @property
    def observation_ids(self):return self.baseline.observation_ids

    @property
    def observation(self):return self.baseline.observation

    @property
    def candidate_count(self):return self.baseline.candidate_count

    @property
    def priors_piecewise_constant(self):return self.baseline.priors_piecewise_constant

    def _state(self, state):
        state=np.asarray(state,dtype=float)
        if state.shape != (self.dimension,) or not np.all(np.isfinite(state)):
            raise ValueError('Invalid discrepancy state')
        local=state[:self.baseline.dimension].copy()
        local[:2]+=state[self.offset_start:self.offset_start+2]
        return local

    def score_all(self,state):return self.baseline.score_all(self._state(state))

    def score_selected(self,state,index):return self.baseline.score_selected(self._state(state),index)

    def predict_selected(self,state,index):
        p=self.baseline.predict_selected(self._state(state),index)
        jacobian=np.zeros((len(self.observation),self.dimension))
        jacobian[:,:self.baseline.dimension]=p.jacobian
        jacobian[:,self.offset_start:self.offset_start+2]=p.jacobian[:,:2]
        return Prediction(p.mean,jacobian,p.covariance,p.eligible)


def augment_window(prepared,sigma_km):
    if not np.isfinite(sigma_km) or sigma_km<=0:
        raise ValueError('Positive fixed discrepancy width required; zero uses baseline')
    binding,scans,columns,precision,ports=prepared
    base=len(precision); dimension=base+2*len(scans)
    result=[];cursor=0
    for j,(_,_,local) in enumerate(scans):
        count=len(local)
        result.extend(DiscrepancyPort(p,base+2*j,dimension) for p in ports[cursor:cursor+count])
        cursor+=count
    if cursor!=len(ports):raise ValueError('Window track counts do not agree')
    return np.r_[precision,np.full(2*len(scans),1/sigma_km**2)],result
