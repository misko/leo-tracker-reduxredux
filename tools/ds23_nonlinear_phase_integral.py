"""Conditional Gaussian evidence correction for nonlinear orbital phase.

Integrate all non-phase Gaussian coordinates analytically. Draw only the
correlated phase marginal, then importance-correct the nominal Doppler mean.
Gamma precisions and the existing orbital-shape design remain conditioned.
This is a diagnostic of that explicit model, not a full hierarchical integral.
"""

import numpy as np
from scipy.special import ndtri,logsumexp
from scipy.stats import qmc

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.frames import geodetic_to_ecef_km


def phase_frequency_samples(bank,times,labels,phases,latitude,longitude):
    t,j,phi=np.asarray(times,float),np.asarray(labels,int),np.asarray(phases,float)
    if t.ndim!=1 or j.shape!=t.shape or phi.ndim!=2 or np.any(j<0) or np.any(j>=phi.shape[1]):
        raise ValueError('times, observation labels and sample-by-family phases required')
    knots=np.asarray(bank['time_s']);phase=phi[:,j];requested=t[None,:]+phase
    if not np.isfinite(requested).all() or np.any(requested<knots[0]) or np.any(requested>knots[-1]):
        raise ValueError('sampled phase interpolation never extrapolates')
    index=np.clip(np.searchsorted(knots,requested,side='right')-1,0,len(knots)-2)
    fraction=(requested-knots[index])/(knots[index+1]-knots[index]);angle=EARTH_ROTATION_RAD_S*phase
    cosine,sine=np.cos(angle),np.sin(angle);states=[]
    for key in ['position_km','velocity_km_s']:
        source=np.asarray(bank[key]);value=source[j[None,:],index]+fraction[:,:,None]*(source[j[None,:],index+1]-source[j[None,:],index])
        x,y=value[:,:,0].copy(),value[:,:,1].copy()
        value[:,:,0]=cosine*x-sine*y;value[:,:,1]=sine*x+cosine*y;states.append(value)
    line=states[0]-geodetic_to_ecef_km(latitude,longitude,0.)
    rate=np.sum(line*states[1],axis=2)/np.linalg.norm(line,axis=2)
    return -11.5e9*rate/299792.458


class ConditionalPhaseIntegral:
    def __init__(self,raw,features,weight,precision,phase_indices):
        self.raw,self.u,self.w,self.precision=map(lambda x:np.asarray(x,float),(raw,features,weight,precision))
        self.phase_indices=np.asarray(phase_indices,int)
        if (self.raw.ndim!=1 or self.u.ndim!=2 or self.u.shape[0]!=len(self.raw)
            or self.w.shape!=self.raw.shape or self.precision.shape!=(self.u.shape[1],)
            or np.any(self.w<=0) or np.any(self.precision<=0)
            or not all(np.isfinite(v).all() for v in [self.raw,self.u,self.w,self.precision])):
            raise ValueError('matched finite Gaussian data, design and positive precisions required')
        gram=np.diag(self.precision)+self.u.T@(self.u*self.w[:,None])
        root=np.linalg.cholesky(gram);inverse=np.linalg.solve(root,np.eye(len(root)))
        covariance=inverse.T@inverse;coefficient=covariance@(self.u.T@(self.w*self.raw))
        self.phase_mean=coefficient[self.phase_indices]
        self.phase_covariance=covariance[np.ix_(self.phase_indices,self.phase_indices)]
        rest=np.ones(len(self.precision),bool);rest[self.phase_indices]=False
        self.rest=self.u[:,rest];self.phase=self.u[:,self.phase_indices]
        self.rest_gram=np.diag(self.precision[rest])+self.rest.T@(self.rest*self.w[:,None])
        self.rest_root=np.linalg.cholesky(self.rest_gram)
        self.conditional_mean=coefficient

    def inverse_rest_covariance(self,value):
        v=np.asarray(value,float);weighted=self.w[:,None]*v if v.ndim==2 else self.w*v
        rhs=self.rest.T@weighted
        fitted=np.linalg.solve(self.rest_root.T,np.linalg.solve(self.rest_root,rhs))
        return weighted-self.w[:,None]*(self.rest@fitted) if v.ndim==2 else weighted-self.w*(self.rest@fitted)

    def log_ratio(self,phase_draws,nonlinear_mean_delta):
        draw=np.asarray(phase_draws,float);delta=np.asarray(nonlinear_mean_delta,float)
        if draw.ndim!=2 or draw.shape[1]!=len(self.phase_indices) or delta.shape!=(len(draw),len(self.raw)):
            raise ValueError('matching phase draws and sample-by-observation mean correction required')
        residual=self.raw[None,:]-draw@self.phase.T
        inverse_delta=self.inverse_rest_covariance(delta.T).T
        return np.sum(residual*inverse_delta-.5*delta*inverse_delta,axis=1)

    def draws(self,samples,seed):
        power=int(np.log2(samples))
        if samples<2 or 2**power!=samples:raise ValueError('power-of-two Sobol sample count required')
        uniform=qmc.Sobol(len(self.phase_indices),scramble=True,seed=seed).random_base2(power)
        z=ndtri(np.clip(uniform,1e-12,1-1e-12))
        return self.phase_mean+z@np.linalg.cholesky(self.phase_covariance).T


def summarize_log_ratio(value):
    logratio=np.asarray(value,float);normal=logsumexp(logratio);weights=np.exp(logratio-normal)
    return dict(negative_twice_log_evidence_correction=float(-2*(normal-np.log(len(logratio)))),
        effective_sample_fraction=float(1/(len(weights)*np.sum(weights**2))),
        maximum_normalized_weight=float(weights.max()),
        log_ratio_range=[float(min(logratio)),float(max(logratio))])
