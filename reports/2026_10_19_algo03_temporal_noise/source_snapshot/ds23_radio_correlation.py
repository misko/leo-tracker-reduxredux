"""Radio-only temporal covariance from polynomial residual contrasts.

REML removes each saved polynomial before learning a shared correlation shape.
Each piece has its own profiled variance; no orbit or geographic residual is
used. This is an uncertainty hypothesis, not a calibrated noise guarantee.
"""

import numpy as np

ALPHAS=(0.,.1,.3,.6,.9)
TAUS=(1.,3.,10.,30.,100.)


def correlation(times,alpha,tau):
    t=np.asarray(times,float)
    if t.ndim!=1 or not np.isfinite(t).all() or not 0<=alpha<1 or not np.isfinite(tau) or tau<=0:
        raise ValueError("finite times, correlation fraction in [0,1), and positive time scale required")
    return (1-alpha)*np.eye(len(t))+alpha*np.exp(-abs(t[:,None]-t)/tau)


def contrasts(times,values,degree):
    t,y=np.asarray(times,float),np.asarray(values,float)
    if t.shape!=y.shape or t.ndim!=1 or len(t)<2*(degree+1)+3 or degree<0:
        raise ValueError("sufficient paired polynomial samples required")
    z=(t-t.mean())/max(1.,float(np.ptp(t)))
    q,_=np.linalg.qr(np.vander(z,degree+1,increasing=True),mode="complete")
    b=q[:,degree+1:]
    return b,b.T@(y-y.mean())


def learn(tracks):
    candidates={(a,t):0. for a in ALPHAS if a for t in TAUS}
    baseline=0.;dimensions=0;pieces=0;seen=set()
    for track in tracks:
        times=np.asarray(track["times"]);values=np.asarray(track["values"])
        for piece in track["pieces"]:
            indices=[k for k,(t,oid) in enumerate(zip(times,track["observation_ids"],strict=True))
                     if piece["start_s"]<=t<=piece["end_s"] and oid not in seen]
            degree=piece["degree"]
            if len(indices)<2*(degree+1)+3:continue
            t=times[indices];b,z=contrasts(t,values[indices],degree);m=len(z)
            energy=float(z@z)
            if energy<=1e-12:continue
            seen.update(track["observation_ids"][k] for k in indices)
            baseline+=m*np.log(energy/m);dimensions+=m;pieces+=1
            for tau in TAUS:
                kernel=np.exp(-abs(t[:,None]-t)/tau)
                eigen,axes=np.linalg.eigh(b.T@kernel@b);eigen=np.maximum(eigen,0.)
                projected=(axes.T@z)**2
                for alpha in ALPHAS[1:]:
                    variance=1-alpha+alpha*eigen
                    candidates[alpha,tau]+=m*np.log(float(np.sum(projected/variance))/m)+np.log(variance).sum()
    if not dimensions:return dict(qualified=False,alpha=0.,tau_s=10.,pieces=0)
    alpha,tau=min(candidates,key=candidates.get);gain=baseline-candidates[alpha,tau]
    penalty=2*np.log(dimensions);qualified=pieces>=10 and gain>penalty
    return dict(qualified=bool(qualified),alpha=alpha if qualified else 0.,tau_s=tau if qualified else 10.,
        radio_REML_gain=float(gain),complexity_penalty=float(penalty),pieces=pieces,residual_contrasts=dimensions,
        candidates=[dict(alpha=a,tau_s=t,cost=float(v)) for (a,t),v in candidates.items()],
        baseline_cost=float(baseline),no_GPS_TLE_or_satellite_residuals_used=True,
        each_original_observation_used_at_most_once_for_noise_learning=True,
        all_original_observations_remain_available_for_position=True)


def whitener(times,sigma,alpha,tau):
    sigma=np.asarray(sigma,float)
    if sigma.shape!=(len(times),) or np.any(sigma<=0) or not np.isfinite(sigma).all():
        raise ValueError("one positive finite marginal noise scale per point required")
    root=np.linalg.cholesky(correlation(times,alpha,tau))
    white=np.linalg.solve(root,np.eye(len(root)))/sigma[None,:]
    return white,float(2*np.log(np.diag(root)).sum()+2*np.log(sigma).sum())
