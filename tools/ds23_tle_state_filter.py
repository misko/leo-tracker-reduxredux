"""Causal along-track phase/rate filter with separate process/measurement noise.

The linear state is relative to a previously available SGP4 orbit. A single
Gamma precision per satellite history scales Gaussian process and measurement
errors, giving exact Student predictive densities within this assumed model.
TLE errors may be correlated or biased; historical diagnostics must qualify
the model before its latent-state moments are used in any RF experiment.
"""

import numpy as np
from scipy.optimize import minimize,minimize_scalar
from scipy.special import gammaln


def student_cost(error, covariance, alpha, beta):
    """-2 log density of a Gaussian mixed over Gamma(alpha,beta) precision."""
    e=np.asarray(error,float);s=np.asarray(covariance,float)
    d=e.shape[-1]
    quadratic=np.einsum('...i,...i->...',e,np.linalg.solve(s,e[...,None])[...,0])
    sign,logdet=np.linalg.slogdet(s)
    if np.any(sign<=0) or np.any(alpha<=1) or np.any(beta<=0):
        raise ValueError('positive covariance, alpha>1 and beta>0 required')
    return (d*np.log(2*np.pi*beta)+logdet+2*gammaln(alpha)-2*gammaln(alpha+d/2)+
            (2*alpha+d)*np.log1p(quadratic/(2*beta)))


def pack(series):
    if not series:
        raise ValueError('nonempty satellite histories required')
    n=len(series);width=max(len(r['times_hours']) for r in series)
    times=np.zeros((n,width));observed=np.zeros((n,width,2));valid=np.zeros((n,width),bool)
    score=np.zeros((n,width),bool);publication=np.zeros((n,width),np.int64)
    for j,row in enumerate(series):
        t=np.asarray(row['times_hours'],float);y=np.asarray(row['observations'],float)
        if len(t)<2 or y.shape!=(len(t),2) or not np.isfinite(y).all() or not np.isfinite(t).all() or np.any(np.diff(t)<=0):
            raise ValueError('at least two increasing finite timestamps and phase/rate vectors required')
        m=len(t);times[j,:m]=t;observed[j,:m]=y;valid[j,:m]=True
        score[j,:m]=row['score_eligible'];publication[j,:m]=row['publication_utc_ns']
    return dict(times=times,observations=observed,valid=valid,score_eligible=score,
        publication=publication,norads=np.array([r['norad'] for r in series]))


def filter_histories(data, parameters, nu=3.):
    """Batch exact Normal-Gamma filtering; time is hours, phase is seconds."""
    rp,rv,sqrtq=np.asarray(parameters,float)
    if not np.isfinite([rp,rv,sqrtq]).all() or min(rp,rv)<0 or sqrtq<=0 or nu<=2:
        raise ValueError('nonnegative measurement noise, positive process noise and nu>2 required')
    y=data['observations'];n,width=data['valid'].shape
    r=np.diag([rp*rp,rv*rv]);q=sqrtq*sqrtq
    mean=y[:,0].copy();cov=np.broadcast_to(r,(n,2,2)).copy()
    alpha=np.full(n,nu/2);beta=np.full(n,(nu-2)/2)
    joint=np.zeros((n,width));phase=np.zeros((n,width));standardized=np.zeros((n,width));white_rate=np.zeros((n,width))
    predicted_mean=np.zeros((n,width));predicted_variance=np.zeros((n,width))
    identity=np.eye(2)
    for k in range(1,width):
        ix=np.flatnonzero(data['valid'][:,k])
        if not len(ix):continue
        dt=data['times'][ix,k]-data['times'][ix,k-1]
        f=np.broadcast_to(identity,(len(ix),2,2)).copy();f[:,0,1]=dt
        process=q*np.array([[dt**3/3,dt**2/2],[dt**2/2,dt]]).transpose(2,0,1)
        m=np.einsum('nij,nj->ni',f,mean[ix]);p=f@cov[ix]@f.transpose(0,2,1)+process
        s=p+r;error=y[ix,k]-m
        joint[ix,k]=student_cost(error,s,alpha[ix],beta[ix])
        phase[ix,k]=student_cost(error[:,:1],s[:,:1,:1],alpha[ix],beta[ix])
        variance=s[:,0,0]*beta[ix]/(alpha[ix]-1)
        standardized[ix,k]=error[:,0]/np.sqrt(variance)
        rate_variance=(s[:,1,1]-s[:,0,1]**2/s[:,0,0])*beta[ix]/(alpha[ix]-1)
        white_rate[ix,k]=(error[:,1]-s[:,0,1]/s[:,0,0]*error[:,0])/np.sqrt(rate_variance)
        predicted_mean[ix,k]=m[:,0];predicted_variance[ix,k]=variance
        gain=np.linalg.solve(s,p.transpose(0,2,1)).transpose(0,2,1)
        mean[ix]=m+np.einsum('nij,nj->ni',gain,error)
        j=identity-gain
        cov[ix]=j@p@j.transpose(0,2,1)+gain@r@gain.transpose(0,2,1)
        alpha[ix]+=1
        beta[ix]+=.5*np.einsum('ni,ni->n',error,np.linalg.solve(s,error[...,None])[...,0])
    last=np.sum(data['valid'],axis=1)-1
    return dict(joint_cost=joint,phase_cost=phase,standardized=standardized,
        predicted_mean=predicted_mean,predicted_variance=predicted_variance,whitened_rate=white_rate,
        posterior_mean=mean,posterior_covariance=cov,alpha=alpha,beta=beta,
        last_hours=data['times'][np.arange(n),last],measurement_covariance=r,
        parameters=list(map(float,parameters)))


def predict_state(result,target_hours):
    dt=np.asarray(target_hours)-result['last_hours']
    if np.any(dt<0) or not np.isfinite(dt).all():
        raise ValueError('state prediction cannot go before the last available observation')
    mean=result['posterior_mean'];p=result['posterior_covariance'];q=result['parameters'][2]**2
    phase=mean[:,0]+dt*mean[:,1]
    variance=p[:,0,0]+2*dt*p[:,0,1]+dt*dt*p[:,1,1]+q*dt**3/3
    scale=result['beta']/(result['alpha']-1)
    return dict(mean=phase,latent_variance=variance*scale,
        next_measurement_variance=(variance+result['measurement_covariance'][0,0])*scale,
        posterior_degrees=2*result['alpha'])


def fit_parameters(data,mask):
    mask=np.asarray(mask,bool)
    if mask.shape!=data['valid'].shape or int(mask.sum())<30 or np.any(mask & ~data['score_eligible']):
        raise ValueError('at least thirty declared historical transitions required')
    bounds=np.log([[.01,3.],[.001,1.],[.0003,1.]])
    starts=[(.1,.03,.01),(.3,.1,.03),(.03,.01,.1),(1.,.3,.3)]
    def objective(log_parameters):
        result=filter_histories(data,np.exp(log_parameters))
        return float(result['joint_cost'][mask].sum())
    fits=[]
    for start in starts:
        fit=minimize(objective,np.log(start),method='L-BFGS-B',bounds=bounds,
            options=dict(maxiter=100,ftol=1e-10))
        fits.append(dict(parameters=np.exp(fit.x).tolist(),cost=float(fit.fun),
            converged=bool(fit.success),message=str(fit.message)))
    valid=[r for r in fits if r['converged']]
    if not valid:raise ValueError('all historical state-filter fits failed')
    return dict(min(valid,key=lambda r:r['cost']),starts=fits,training_transitions=int(mask.sum()),
        parameter_names=['measurement_phase_sd_s','measurement_rate_sd_s_per_hour','sqrt_process_intensity_s_per_hour_1p5'])


def fit_measurement_off(data,mask):
    fit=minimize_scalar(lambda x:float(filter_histories(data,[0.,0.,np.exp(x)])['joint_cost'][mask].sum()),
        bounds=np.log([.0003,1.]),method='bounded',options=dict(xatol=1e-7))
    if not fit.success:raise ValueError('measurement-off historical fit failed')
    return dict(parameters=[0.,0.,float(np.exp(fit.x))],cost=float(fit.fun),converged=True)


def residual_diagnostics(z,mask):
    clipped=np.clip(z,-3,3);selected=clipped[mask]
    paired=mask[:,1:] & mask[:,:-1]
    left=clipped[:,:-1][paired];right=clipped[:,1:][paired]
    correlation=float(np.corrcoef(left,right)[0,1]) if len(left)>=30 else None
    return dict(count=len(selected),winsorized_mean=float(np.mean(selected)),
        adjacent_pairs=len(left),winsorized_adjacent_correlation=correlation,
        compatible=bool(len(selected)>=30 and abs(np.mean(selected))<.25 and
            correlation is not None and abs(correlation)<.2))
