"""Conditional residual-gate simulations at frozen physical designs.

This is a Gaussian, fixed-precision surrogate. It does not repeat satellite
search, mask selection, nonlinear position fitting or phase relinearization.
"""

from dataclasses import dataclass
import numpy as np
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def gate_score(residual,times):
    r=np.asarray(residual,float);t=np.asarray(times,float)
    d=batch_noise_screen(r.T,t)
    scores=np.column_stack((d['mean_z']/3,d['slope_z']/3,d['quadratic_bic_gain']/10,
        d['maximum_step_z']/4,abs(d['lag1_acf'])*np.sqrt(len(t))/4))
    return np.max(scores,axis=1)


def profiled(raw,bias_sigma):
    r=np.asarray(raw,float)
    # The legacy whitening matrix is I/150; its reported innovations are Hz.
    return r-r.sum(axis=0)[None,:]/(len(r)+150.**2/bias_sigma**2)


def calibration_cutoff(scores,alpha=.05):
    s=np.asarray(scores,float)
    if s.ndim!=1 or not len(s) or not np.isfinite(s).all() or not 0<alpha<1:
        raise ValueError('finite calibration scores and alpha in (0,1) required')
    rank=int(np.ceil((len(s)+1)*(1-alpha)))
    if rank>len(s):raise ValueError('too few calibration draws for requested tail')
    return max(1.,float(np.sort(s)[rank-1]))


@dataclass
class GateState:
    features: np.ndarray
    prior_precision: np.ndarray
    weight: np.ndarray
    mean: np.ndarray
    coefficient: np.ndarray
    curved: list
    linear_features: np.ndarray
    linear: list
    constant_start: int
    original_members: int

    def __post_init__(self):
        u=self.features;self.gram=np.diag(self.prior_precision)+u.T@(u*self.weight[:,None])
        self.root=np.linalg.cholesky(self.gram)

    def solve(self,rhs):
        return np.linalg.solve(self.root.T,np.linalg.solve(self.root,rhs))

    def residuals(self,noise,linear_noise,bias,mode='fitted_centered',injection=None,linear_injection=None):
        e=np.asarray(noise,float);el=np.asarray(linear_noise,float)
        if injection is not None:e=e+np.asarray(injection)[:,None]
        if linear_injection is not None:el=el+np.asarray(linear_injection)[:,None]
        if mode not in ('white','fitted_centered','fitted_plugin'):raise ValueError('unknown null model')
        offset=self.coefficient-self.mean if mode=='fitted_plugin' else np.zeros_like(self.mean)
        if mode=='white':fit=np.broadcast_to(self.mean[:,None],(len(self.mean),e.shape[1]))
        else:
            raw=e+(self.features@offset)[:,None]
            fit=self.mean[:,None]+self.solve(self.features.T@(raw*self.weight[:,None]))
        truth=self.mean+offset
        rc=e+self.features@(truth[:,None]-fit)
        rl=el+self.linear_features@(truth[:,None]-fit)+bias
        return rc,rl,fit

    def score_residuals(self,rc,rl,fit):
        result=np.zeros(rc.shape[1])
        for track in self.curved:
            sl=track['slice'];r=rc[sl]
            result=np.maximum(result,gate_score(r,track['times']))
            raw=r+1000.*fit[self.constant_start+track['member_index']][None,:]
            result=np.maximum(result,gate_score(profiled(raw,1000.),track['times']))
        for track in self.linear:
            result=np.maximum(result,gate_score(profiled(rl[track['slice']],300.),track['times']))
        return result

    def scores(self,*args,**kwargs):
        return self.score_residuals(*self.residuals(*args,**kwargs))


def unit_shape(times,kind):
    t=np.asarray(times,float);x=(t-t.mean())/max(float(np.ptp(t)),1.)
    if kind=='slope':v=x
    elif kind=='quadratic':
        v=x*x;design=np.column_stack((np.ones(len(x)),x));v-=design@np.linalg.lstsq(design,v,rcond=None)[0]
    elif kind=='step':v=(t>=np.median(t)).astype(float);v-=v.mean()
    else:raise ValueError('unknown injected shape')
    scale=np.sqrt(np.mean(v*v))
    if scale<1e-12:raise ValueError('insufficient time support for injected shape')
    return v/scale


def injection(state,kind):
    largest=max(state.curved,key=lambda t:len(t['times']))
    c=np.zeros(len(state.features));l=np.zeros(len(state.linear_features))
    if kind in ('slope','quadratic','step'):
        c[largest['slice']]=unit_shape(largest['times'],kind)
    elif kind in ('receiver_quadratic','satellite_quadratic'):
        key='receiver' if kind=='receiver_quadratic' else 'candidate_index';selected=largest[key]
        def shape(t):return ((np.asarray(t)-150.)/150.)**2
        times=np.concatenate([t['times'] for t in state.curved if t[key]==selected])
        center=float(shape(times).mean());scale=float(np.std(shape(times)))
        for tracks,values in ((state.curved,c),(state.linear,l)):
            for track in tracks:
                if track[key]==selected:values[track['slice']]=(shape(track['times'])-center)/max(scale,1e-12)
    else:raise ValueError('unknown shared injection')
    return c,l
