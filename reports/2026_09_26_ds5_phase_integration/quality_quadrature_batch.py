"""Batched fixed-offset integration with scaled exact quality-state recursion."""
import numpy as np
from scipy.special import roots_hermitenorm,logsumexp

def batch_evidence(residuals,scales,times,flags,nodes=32,warmup=8):
    """Return model,hypothesis,time log evidences; held begins after warmup.

    Offset quadrature uses only the warmup observations. Scaling the quality
    recursion per offset node avoids both log-domain overhead and underflow.
    The two returned models are generic and timing_informed, respectively.
    """
    residuals=np.asarray(residuals,float);scales=np.asarray(scales,float);q=len(scales);h,n=residuals.shape;warmup=min(warmup,n)
    x,w=roots_hermitenorm(nodes);live=w>0;x=x[live];w=w[live]/np.sqrt(2*np.pi)
    centers=np.stack([residuals[:,:warmup].mean(axis=-1),np.median(residuals[:,:warmup],axis=-1)],axis=-1)
    means=np.repeat(centers,q,axis=-1);sd=np.tile(scales/np.sqrt(warmup),2)
    beta=(means[:,:,None]+sd[None,:,None]*x[None,None,:]).reshape(h,-1)
    proposal=logsumexp(-.5*((beta[:,:,None]-means[:,None,:])/sd[None,None,:])**2-np.log(sd[None,None,:]*np.sqrt(2*np.pi)),axis=-1)-np.log(len(sd))
    weights=np.tile(np.log(w)-np.log(len(sd)),len(sd))[None,:]-.5*(beta/1e6)**2-np.log(1e6*np.sqrt(2*np.pi))-proposal
    state=np.full((2,h,beta.shape[-1],q),1/q);logscale=np.zeros((2,h,beta.shape[-1]));out=[]
    for i in range(n):
        hazard=0. if not i else -np.expm1(-(times[i]-times[i-1])/20.)
        hazards=np.array([hazard,1-(1-hazard)*.5 if i and flags[i-1] else hazard])
        state=state*(1-hazards[:,None,None,None])+hazards[:,None,None,None]/q
        emission=-.5*((residuals[:,i,None,None]-beta[:,:,None])/scales[None,None,:])**2-np.log(scales[None,None,:]*np.sqrt(2*np.pi))
        peak=emission.max(axis=-1);state*=np.exp(emission-peak[:,:,None])[None,:,:,:]
        normalizer=state.sum(axis=-1)
        if not np.all(normalizer>0):raise FloatingPointError('quality forward normalization underflow')
        state/=normalizer[:,:,:,None];logscale+=np.log(normalizer)+peak[None,:,:]
        out.append(logsumexp(weights[None,:,:]+logscale,axis=-1))
    return np.stack(out,axis=-1)
