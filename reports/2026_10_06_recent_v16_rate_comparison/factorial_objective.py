"""Cone-only extension of the original hard-horizon T1-AT/V16 score.

Unlike the earlier cone experiment, this does NOT also change horizon gating.
Frozen shared-shape/independent-roll cone; strength .5, floor .1; same total
detection mass per window. No cone fitting to this cohort or missing-RX veto.
"""
from functools import lru_cache
import json
from pathlib import Path
import sys
import numpy as np
import process_stage as stage

from numeric_data import enable_research_model
enable_research_model()
CONE = stage.ROOT/'reports/2026_10_05_cone_prior_localization'
GEOMETRY = stage.ROOT/'reports/2026_10_05_receiver_cones'
from position_score_sweep import Objective as Base
sys.path[:0] = [str(CONE),str(GEOMETRY)]
from cone_objective import Objective as OldCone
from cone_geometry import Support, tilt
from cone_model import frame, BORESIGHTS_DEG
from smooth_visibility_model import finite_set_terms


@lru_cache(maxsize=1)
def bundle():
    summary=json.loads((GEOMETRY/'summary.json').read_text())
    with np.load(GEOMETRY/'sky-maps.npz',allow_pickle=False) as z:
        support=Support(z['inside'],z['supported'])
    return np.array(summary['primary']['theta']),np.array([frame(*b) for b in BORESIGHTS_DEG]),support


class Likelihood:
    def __init__(self,data,features,spec):
        self.measured=data.measured;self.features=features
        self.coefficients=np.zeros(features.shape[1]);self.weights=np.ones(len(data.times))
        self.alias_hz=1/4.4e-6;self.clutter_rate=spec['clutter_rate']
        self.detection_probability=spec['detection_budget']/len(data.numbers)
        self.log_factor=None;self.last_result=None

    def evaluate(self,predicted,visible,*,sigma_hz,**unused):
        base=self.detection_probability*np.asarray(visible,float)
        q=tilt(base,self.log_factor)
        result=finite_set_terms(self.measured,predicted+(self.features@self.coefficients)[:,None],
                               q,self.weights,sigma_hz,self.clutter_rate)
        _,_,derivative=tilt(base,self.log_factor,-result['probability_gradient'])
        result['log_factor_loss_gradient']=derivative
        self.last_result=result
        return result


class Objective(Base):
    geometry=OldCone.geometry

    def __init__(self,data,center,arm,spec,*,strength=.5):
        super().__init__(data,center,arm,spec)
        self.data=data;self.strength=strength
        self.theta,self.frames,self.support=bundle()
        self.cache_key=None;self.geometry_cache=None
        self.likelihood=Likelihood(data,self.features,spec)
        self.base.likelihood=self.likelihood

    def evaluate(self,vector):
        self.base.check_deadline()
        state=self.base.state(np.asarray(vector[:self.size]))
        if not state['ephemeris_valid']: return super().evaluate(vector)
        _,dp,dt,loga,ja=self.geometry(state['parameters'])
        self.likelihood.log_factor=loga
        value,gradient=super().evaluate(vector)
        dunit=ja*self.likelihood.last_result['log_factor_loss_gradient'][...,None]
        physical=np.zeros(6+len(self.data.numbers))
        physical[:2]=np.einsum('nkj,nkjd->d',dunit,dp)
        physical[6:]=np.sum(dunit*dt,axis=(0,2))
        gradient[:self.size]+=self.base.vector_gradient(physical,vector[:self.size])
        return value,gradient
