"""Sequential catalogue likelihood with an approximate latent CFO-quality filter."""
import numpy as np
from scipy.special import logsumexp

def run_filter(residuals,logprior,scales,times,pilot_flags,kind='stationary',warmup=8):
    """Gaussian moment matching over quality histories; identity/time stay fixed.

    Residual shape: candidate, orbit-time, observation. Quality changes only
    redistribute conditional scale weights, never catalogue identity weights.
    Flags from observation i affect prediction of i+1, not its own likelihood.
    """
    scales=np.asarray(scales,float);variance=scales**2
    logw=np.broadcast_to(logprior[...,None]-np.log(len(scales)),(*logprior.shape,len(scales))).copy();logw-=logsumexp(logw)
    mean=np.zeros_like(logw);var=np.full_like(logw,1e12);rows=[]
    for i,t in enumerate(times):
        hazard=0.
        if i and kind!='stationary':hazard=-np.expm1(-(t-times[i-1])/20.)
        if i and kind=='timing_informed' and pilot_flags[i-1]:hazard=1-(1-hazard)*.5
        if hazard:
            mass=logsumexp(logw,axis=-1,keepdims=True);q=np.exp(logw-mass)
            overall_mean=np.sum(q*mean,axis=-1,keepdims=True)
            overall_var=np.sum(q*(var+(mean-overall_mean)**2),axis=-1,keepdims=True)
            mixed=np.logaddexp(logw+np.log1p(-hazard),mass+np.log(hazard/len(scales)))
            stay=np.exp(logw+np.log1p(-hazard)-mixed)
            newmean=stay*mean+(1-stay)*overall_mean
            var=stay*(var+(mean-newmean)**2)+(1-stay)*(overall_var+(overall_mean-newmean)**2)
            mean=newmean;logw=mixed
        innovation=residuals[...,i,None]-mean;predictive_var=var+variance
        ll=-.5*(np.log(2*np.pi*predictive_var)+innovation**2/predictive_var)
        score=float(logsumexp(logw+ll));logw+=ll-score
        gain=var/predictive_var;mean+=gain*innovation;var=var*variance/predictive_var
        identity=np.exp(logsumexp(logw,axis=(1,2)));quality=np.exp(logsumexp(logw,axis=(0,1)))
        rows.append(dict(index=i,time_s=float(t),held=i>=warmup,log_predictive=score,transition_probability=float(hazard),top_candidate_index=int(np.argmax(identity)),identity_probabilities=identity.tolist(),scale_probabilities=quality.tolist()))
    return rows
