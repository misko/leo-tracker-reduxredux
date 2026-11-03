"""Analytic Gaussian CFO profile: endpoint of the observation-robustness study."""
import hashlib
import importlib.util
import math
from pathlib import Path
import sys
import numpy as np
from scipy.special import logsumexp

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import ds7_baseline_adapter as baseline


def profile(values,scale):
    values=np.asarray(values,dtype=float)
    variance=scale**2
    n=values.shape[1]
    offset=values.sum(axis=1)/(n+variance/1e12)
    residual=values-offset[:,None]
    score=-.5*np.sum(residual**2,axis=1)/variance-n*math.log(scale*math.sqrt(2*math.pi))-.5*offset**2/1e12
    return score,residual/variance,offset


class GaussianPosition:
    def __init__(self,documents,config,scale,weights=None,factory=baseline.Stationary):
        if len(documents)!=1:
            raise ValueError('Single recording required')
        self.document=documents[0]
        self.geometry=factory(self.document,config)
        self.scale=scale
        self.weights=np.ones(len(self.document['tracks'])) if weights is None else np.asarray(weights)
        if self.weights.shape!=(len(self.document['tracks']),) or not np.isfinite(self.weights).all() or np.any(self.weights<=0):
            raise ValueError('One finite positive weight per track required')
        self.metadata=dict(observation_model='normalized Gaussian',scale_hz=scale,
                           cfo_prior_variance_hz2=1e12,composite_weighting=weights is not None)

    def evaluate(self,x,gradient=True):
        x=np.asarray(x,dtype=float)
        total=0.
        derivative=np.zeros(3)
        for weight,track in zip(self.weights,self.document['tracks']):
            mask=track['mask']
            prediction,visible=self.geometry.prediction(track,x)
            scores,influence,_=profile(track['y'][None,mask]-prediction[:,mask],self.scale)
            scores=np.where(visible,scores,-np.inf)
            normal=logsumexp(scores)
            if not np.isfinite(normal):
                raise ValueError('No finite visible candidate')
            total+=float(weight*(normal-math.log(track['catalogue_size'])))
            if gradient:
                responsibilities=np.exp(scores-normal)
                for axis,step in enumerate((1e-4,1e-4,1e-5)):
                    delta=np.eye(3)[axis]*step
                    plus,minus=x+delta,x-delta
                    if axis==2:
                        plus[axis]=min(5.,plus[axis]);minus[axis]=max(-5.,minus[axis])
                    pp,vp=self.geometry.prediction(track,plus)
                    pm,vm=self.geometry.prediction(track,minus)
                    assert np.array_equal(vp,visible) and np.array_equal(vm,visible)
                    dp=(pp[:,mask]-pm[:,mask])/(plus[axis]-minus[axis])
                    derivative[axis]+=float(weight*responsibilities@np.sum(influence*dp,axis=1))
        return dict(score=total,gradient=derivative)


def build_model(documents,config,variant,index=None):
    if variant not in ('gaussian200','gaussian400','source_gaussian200'):
        raise ValueError(variant)
    scale=400. if variant=='gaussian400' else 200.
    weights=None
    metadata={}
    if variant=='source_gaussian200':
        path=HERE.parent/'source_balance/model.py'
        spec=importlib.util.spec_from_file_location('gaussian_source_balance',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        original=module.build_model(documents,config,'source_receiver_equal',index=index)
        weights=original.weights
        metadata=original.metadata
    model=GaussianPosition(documents,config,scale,weights)
    model.metadata['source_grouping']=metadata
    if variant=='source_gaussian200':
        model.metadata['source_balance_model_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    return model
