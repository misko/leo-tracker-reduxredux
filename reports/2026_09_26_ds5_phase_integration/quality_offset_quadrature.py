"""Independent offset integration reference; no Gaussian history compression."""
import numpy as np
from scipy.special import roots_hermitenorm,logsumexp

def offset_evidence(residual,scales,times,flags,kind,nodes=64,warmup=8):
    """Return prefix log evidence on a grid proposed by the warm-up only.

    Prefixes before warm-up are not certified by this proposal. Held scoring
    uses successive evidence differences beginning after warm-up. Conditional
    on a fixed offset node, the quality-state forward recursion is exact.
    """
    residual=np.asarray(residual,float);scales=np.asarray(scales,float);warmup=min(warmup,len(residual));q=len(scales)
    x,w=roots_hermitenorm(nodes);live=w>0;x=x[live];w=w[live]/np.sqrt(2*np.pi)
    centers=np.array([residual[:warmup].mean(),np.median(residual[:warmup])]);widths=scales/np.sqrt(warmup)
    means=np.repeat(centers,q);sd=np.tile(widths,2)
    beta=(means[:,None]+sd[:,None]*x).ravel()
    logproposal=logsumexp(-.5*((beta[:,None]-means[None,:])/sd[None,:])**2-np.log(sd[None,:]*np.sqrt(2*np.pi)),axis=-1)-np.log(len(means))
    weights=np.tile(np.log(w)-np.log(len(means)),len(means))
    weights+=-.5*(beta/1e6)**2-np.log(1e6*np.sqrt(2*np.pi))-logproposal
    forward=np.full((len(beta),q),-np.log(q));evidence=[]
    for i,r in enumerate(residual):
        h=0. if not i or kind=='stationary' else -np.expm1(-(times[i]-times[i-1])/20)
        if i and kind=='timing_informed' and flags[i-1]:h=1-(1-h)*.5
        if h:forward=np.logaddexp(forward+np.log1p(-h),logsumexp(forward,axis=-1,keepdims=True)+np.log(h/q))
        forward+=-.5*((r-beta[:,None])/scales[None,:])**2-np.log(scales[None,:]*np.sqrt(2*np.pi))
        evidence.append(float(logsumexp(weights+logsumexp(forward,axis=-1))))
    return np.array(evidence)
