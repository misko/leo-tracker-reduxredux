"""Normalized paired detection emissions and a continuous-time presence model.

The observed bits are source-specific latent-assignment outcomes, not merely
whether a probe contains any candidate. Unknown RX observations are marginalized.
"""
import numpy as np
from numpy.polynomial.hermite import hermgauss
from scipy.special import expit,logsumexp

def state_probabilities(logits,shared_strength_sd=0.,order=24):
    logits=np.asarray(logits,dtype=float)
    if logits.ndim<1 or logits.shape[-1]!=2 or not np.isfinite(logits).all():raise ValueError('expected finite paired logits')
    if not np.isfinite(shared_strength_sd) or shared_strength_sd<0:raise ValueError('invalid strength scale')
    nodes,weights=hermgauss(order);weights=weights/np.sqrt(np.pi)
    p=expit(logits[...,None,:]+np.sqrt(2)*shared_strength_sd*nodes[:,None])
    a,b=p[...,0],p[...,1]
    # Bit 0 is RX0, bit 1 RX1. Shared strength induces receiver dependence.
    states=np.stack(((1-a)*(1-b),a*(1-b),(1-a)*b,a*b),axis=-1)
    return np.sum(states*weights[:,None],axis=-2)

def emission(probabilities,bits):
    p=np.asarray(probabilities,dtype=float);bits=np.asarray(bits)
    if p.ndim!=3 or p.shape[-1]!=4 or bits.shape!=(len(p),2):raise ValueError('expected W,K,4 probabilities and W,2 observations')
    if not np.isfinite(p).all() or (p<0).any() or not np.allclose(p.sum(axis=-1),1,atol=1e-10):raise ValueError('probabilities must normalize')
    if not np.isin(bits,[-1,0,1]).all():raise ValueError('unknown=-1, absent=0, detected=1')
    allowed=np.ones((len(p),4),bool)
    for receiver in (0,1):
        state_bit=(np.arange(4)>>receiver)&1
        allowed&=(bits[:,receiver,None]<0)|(bits[:,receiver,None]==state_bit)
    value=np.sum(p*allowed[:,None,:],axis=-1)
    with np.errstate(divide='ignore'):return np.log(value)

def presence_score(times,present_loglik,absent_loglik,occupancy,tau_s,observed=None):
    times=np.asarray(times,dtype=float);present=np.asarray(present_loglik,dtype=float);absent=np.asarray(absent_loglik,dtype=float)
    if times.ndim!=1 or present.ndim!=2 or present.shape[0]!=len(times) or absent.shape!=(len(times),):raise ValueError('invalid presence shapes')
    if not np.isfinite(times).all() or (np.diff(times)<0).any() or not 0<occupancy<1 or not np.isfinite(tau_s) or tau_s<=0:raise ValueError('invalid times or presence prior')
    if np.isnan(present).any() or np.isposinf(present).any() or np.isnan(absent).any() or np.isposinf(absent).any():raise ValueError('invalid emission score')
    observed=np.ones(len(times),bool) if observed is None else np.asarray(observed,dtype=bool)
    if observed.shape!=times.shape:raise ValueError('mask mismatch')
    stationary=np.array([1-occupancy,occupancy]);alpha=np.broadcast_to(np.log(stationary),(present.shape[1],2)).copy()
    for i,t in enumerate(times):
        if i:
            persistence=np.exp(-(t-times[i-1])/tau_s)
            transition=persistence*np.eye(2)+(1-persistence)*stationary[None,:]
            with np.errstate(divide='ignore'):alpha=logsumexp(alpha[:,:,None]+np.log(transition)[None,:,:],axis=1)
        if observed[i]:alpha+=np.column_stack((np.full(present.shape[1],absent[i]),present[i]))
    return logsumexp(alpha,axis=1)

def beam_logits(los_enu,tilt_deg,intercepts,slope):
    los=np.asarray(los_enu,dtype=float);intercepts=np.asarray(intercepts,dtype=float)
    if los.shape[-1]!=3 or intercepts.shape!=(2,) or not np.isfinite(los).all() or not np.isfinite(intercepts).all():raise ValueError('invalid LOS or receiver offsets')
    if not np.isfinite(tilt_deg) or not np.isfinite(slope) or slope<0:raise ValueError('invalid beam parameters')
    tilt=np.radians(tilt_deg)
    boresights=np.array([[-np.sin(tilt),0,np.cos(tilt)],[np.sin(tilt),0,np.cos(tilt)]])
    return intercepts+slope*(los@boresights.T)
