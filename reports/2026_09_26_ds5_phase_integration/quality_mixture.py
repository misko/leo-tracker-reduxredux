"""Gaussian-sum quality filter: update individual histories before merging."""
import numpy as np
from scipy.special import logsumexp

def compress(logw,mean,var,k):
    """Keep mass and two moments in offset-ordered equal-mass groups."""
    h=logw.shape[0];ow=np.full((h,k),-np.inf);om=np.zeros((h,k));ov=np.ones((h,k))
    live=np.flatnonzero(np.any(np.isfinite(logw),axis=0))
    if len(live)<=k:
        ow[:,:len(live)]=logw[:,live];om[:,:len(live)]=mean[:,live];ov[:,:len(live)]=var[:,live]
        return ow,om,ov
    order=np.argsort(mean,axis=-1);lw=np.take_along_axis(logw,order,-1);mu=np.take_along_axis(mean,order,-1);v=np.take_along_axis(var,order,-1)
    mass=logsumexp(lw,axis=-1,keepdims=True);p=np.exp(lw-mass)
    group=np.minimum(k-1,np.floor((np.cumsum(p,axis=-1)-.5*p)*k).astype(int))
    for j in range(k):
        w=np.where(group==j,p,0.);total=w.sum(axis=-1);safe=np.maximum(total,1e-300)
        m=(w*mu).sum(axis=-1)/safe;variance=(w*(v+(mu-m[:,None])**2)).sum(axis=-1)/safe
        ow[:,j]=np.where(total>0,mass[:,0]+np.log(safe),-np.inf);om[:,j]=m;ov[:,j]=np.where(total>0,variance,1.)
    return ow,om,ov

def run_mixture(residuals,logprior,scales,times,pilot_flags,kind='generic',warmup=8,components=4):
    c,t=logprior.shape;h=c*t;q=len(scales);k=components
    if k<1:raise ValueError('positive component count required')
    residuals=residuals.reshape(h,-1);noise=np.asarray(scales,float)**2
    logw=np.full((h,q,k),-np.inf);logw[:,:,0]=logprior.reshape(h,1)-np.log(q);logw-=logsumexp(logw)
    mean=np.zeros_like(logw);var=np.full_like(logw,1e12);rows=[]
    for i,epoch in enumerate(times):
        hazard=0. if not i or kind=='stationary' else -np.expm1(-(epoch-times[i-1])/20.)
        if i and kind=='timing_informed' and pilot_flags[i-1]:hazard=1-(1-hazard)*.5
        if hazard==0:
            innovation=residuals[:,i,None,None]-mean;pv=var+noise[None,:,None]
            logw+=-.5*(np.log(2*np.pi*pv)+innovation**2/pv)
            mean+=var/pv*innovation;var=var*noise[None,:,None]/pv
        else:
            nw=np.empty_like(logw);nm=np.empty_like(mean);nv=np.empty_like(var)
            lw=logw.reshape(h,q*k);mu=mean.reshape(h,q*k);v=var.reshape(h,q*k);innovation=residuals[:,i,None]-mu
            for state in range(q):
                transition=np.full(q,hazard/q);transition[state]+=1-hazard
                pv=v+noise[state];post=lw+np.repeat(np.log(transition),k)[None,:]-.5*(np.log(2*np.pi*pv)+innovation**2/pv)
                pm=mu+v/pv*innovation;vv=v*noise[state]/pv
                nw[:,state],nm[:,state],nv[:,state]=compress(post,pm,vv,k)
            logw,mean,var=nw,nm,nv
        score=float(logsumexp(logw));logw-=score
        identity=np.exp(logsumexp(logw.reshape(c,t,q,k),axis=(1,2,3)));quality=np.exp(logsumexp(logw,axis=(0,2)))
        rows.append(dict(index=i,time_s=float(epoch),held=i>=warmup,log_predictive=score,transition_probability=float(hazard),top_candidate_index=int(np.argmax(identity)),identity_probabilities=identity.tolist(),scale_probabilities=quality.tolist()))
    return rows
