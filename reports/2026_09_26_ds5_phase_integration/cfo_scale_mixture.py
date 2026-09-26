"""Marginalize a per-track CFO scale before phase/timing integration."""
import numpy as np
import hashlib,json
from scipy.special import logsumexp
from catalogue_trial import constant_log_evidence
from timing_trial import quantile_indices
from scipy.interpolate import CubicSpline
from timing_prior import discrete_weights

_PRIOR_CACHE={}

def refine_bank(bank,model,step):
    old=bank['taus'];grid=np.linspace(old[0],old[-1],round((old[-1]-old[0])/step)+1)
    key=(hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest(),old.tobytes(),grid.tobytes())
    if key not in _PRIOR_CACHE:
        _PRIOR_CACHE[key]=[(discrete_weights(model,b['lower_h']+.01,old)[0],discrete_weights(model,b['lower_h']+.01,grid)[0]) for b in model['bins']]
    result=dict(bank)
    for field in ('train_residual','held_residual','projection'):
        result[field]=CubicSpline(old,bank[field],axis=1)(grid)
    priors=[]
    for lp in bank['logprior']:
        if not np.isfinite(lp).all():raise ValueError('refinement requires a separately modeled visibility mask')
        matches=[new for previous,new in _PRIOR_CACHE[key] if np.allclose(previous,lp,rtol=0,atol=1e-9)]
        if not matches:raise ValueError('bank prior does not match the frozen historical model')
        assert all(np.allclose(matches[0],m,rtol=0,atol=1e-9) for m in matches)
        priors.append(matches[0])
    result['logprior']=np.array(priors);result['taus']=grid
    return result

def mixed_options(bank,scales,n=33):
    scales=np.asarray(scales,float)
    if scales.ndim!=1 or len(scales)==0 or np.any(scales<=0):raise ValueError('positive scale grid required')
    full=np.concatenate([bank['train_residual'],bank['held_residual']],axis=-1)
    tr=np.stack([constant_log_evidence(bank['train_residual'],s) for s in scales]);joint=np.stack([constant_log_evidence(full,s) for s in scales])
    # Equal mass on a declared logarithmically spaced discrete grid.
    tr_mix=logsumexp(tr,axis=0)-np.log(len(scales));joint_mix=logsumexp(joint,axis=0)-np.log(len(scales))
    train=logsumexp(tr_mix+bank['logprior'],axis=-1)
    scale_evidence=logsumexp(tr+bank['logprior'][None,:,:],axis=(1,2));scale_prob=np.exp(scale_evidence-logsumexp(scale_evidence));out=[]
    for i in range(len(train)):
        lp=tr_mix[i]+bank['logprior'][i];lp-=logsumexp(lp);ix=quantile_indices(lp,n);jx=quantile_indices(joint_mix[i]+bank['logprior'][i],n)
        per_scale=logsumexp(tr[:,i,:]+bank['logprior'][i],axis=-1);per_scale=np.exp(per_scale-logsumexp(per_scale))
        out.append(dict(candidate_id=str(bank['candidate_ids'][i]),train=float(train[i]),held=float(logsumexp(joint_mix[i]+bank['logprior'][i])-train[i]),sample_held=joint_mix[i,ix]-tr_mix[i,ix],projection=bank['projection'][i,ix],joint_projection=bank['projection'][i,jx],scale_probabilities=per_scale.tolist()))
    return out,dict(scales_hz=scales.tolist(),training_scale_probabilities=scale_prob.tolist(),candidates=len(out))
