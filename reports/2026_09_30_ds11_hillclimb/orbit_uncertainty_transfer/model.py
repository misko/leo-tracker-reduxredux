"""Normalized finite symmetric revision-direction mixture."""
import numpy as np
from scipy.special import gammaln,logsumexp

MAGNITUDES=np.array([0.,.01,.03,.1,.3,1.])
BETA=np.r_[0.,np.column_stack((-MAGNITUDES[1:],MAGNITUDES[1:])).ravel()]
LOG_C=float(gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.))


def track_scores(times,residual,direction,mask):
    t=np.asarray(times,dtype=float);r=np.asarray(residual,dtype=float);d=np.asarray(direction,dtype=float);m=np.asarray(mask,bool)
    r=r-r[m].mean();d=d-d[m].mean();t=t-t[m].mean()
    rms=float(np.sqrt(np.mean(d[m]**2)))
    line=np.zeros_like(d)
    if rms>1e-6:
        assert np.dot(t[m],t[m])>0
        slope=np.dot(t[m],d[m])/np.dot(t[m],t[m])
        sign=-1 if slope<0 else 1
        line=sign*t*rms/np.sqrt(np.mean(t[m]**2))
    result={}
    for name,curve in (('orbit',d),('linear',line)):
        error=r[None,:]-BETA[:,None]*curve[None,:]
        density=LOG_C-2.5*np.log1p((error/100.)**2/4)
        result[name]=dict(train=density[:,m].sum(axis=1),joint=density.sum(axis=1))
    return result,rms


def magnitude_scores(states):
    return np.column_stack((states[:,0],*[logsumexp(states[:,i:i+2],axis=1)-np.log(2.) for i in range(1,len(BETA),2)]))


def fit_prior(training):
    components=magnitude_scores(np.asarray(training))
    weights=np.ones(6)/6
    for iteration in range(10000):
        logits=components+np.log(weights)
        responsibility=np.exp(logits-logsumexp(logits,axis=1)[:,None])
        new=responsibility.mean(axis=0)
        change=float(np.max(abs(new-weights)))
        weights=new
        if change<1e-10:break
    return dict(weights=weights.tolist(),iterations=iteration+1,converged=change<1e-10,maximum_weight_change=change,
                training_log_score=float(logsumexp(components+np.log(weights),axis=1).sum()))


def predictive(train,joint,weights):
    weights=np.asarray(weights)
    # Tiny positive EM weights may underflow to zero; log(0) is exactly -inf.
    with np.errstate(divide='ignore'):
        logweights=np.log(weights)
    return float(logsumexp(magnitude_scores(np.asarray(joint)[None,:])[0]+logweights)-
                 logsumexp(magnitude_scores(np.asarray(train)[None,:])[0]+logweights))
