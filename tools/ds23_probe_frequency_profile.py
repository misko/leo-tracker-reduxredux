"""Descriptive within-probe CFO profiles with independent frame phases.

Conditional local Gaussian scales omit uncertainty in whole-probe code/timing
parameters. No frequency profile is assumed to be an orbital measurement or a
validated hardware settling correction.
"""

import numpy as np


def frequency_only_fit(p, start, *, radius_hz=800., iterations=16):
    parameters=np.asarray(start,float).copy();center=parameters[[0,3]].copy();active=np.array([0,3])
    current=p.statistics(parameters);damping=1e-3
    for _ in range(iterations):
        normal=current['normal'][np.ix_(active,active)];rhs=current['rhs'][active]
        diagonal=np.maximum(np.diag(normal),current['raw_energy']*1e-14);improved=False
        for _ in range(5):
            step=np.linalg.solve(normal+damping*np.diag(diagonal),rhs)
            step/=max(1.,float(np.max(abs(step)/.8)))
            proposed=parameters.copy();proposed[active]=np.clip(parameters[active]+100*step,center-radius_hz,center+radius_hz)
            if np.max(abs(proposed[active]-parameters[active]))<.1:break
            candidate=p.statistics(proposed)
            if candidate['score']>current['score']+1e-12:
                parameters,current=proposed,candidate;damping=max(1e-8,damping/3);improved=True;break
            damping*=10
        if not improved:break
    noise=current['squared_error']/(current['samples']-17*len(p.segments)-2)
    covariance=noise/2*np.linalg.inv(current['normal'][np.ix_(active,active)])*100**2
    return dict(parameters=parameters,CFO_hz=parameters[active],covariance_hz2=covariance,
        squared_error=current['squared_error'],samples=current['samples'],
        search_boundary=bool(np.max(abs(parameters[active]-center))>=radius_hz-.5))


def effective_times(p,parameters):
    (a,_),(b,_)=[p.columns_and_derivatives(v,k) for k,v in enumerate(np.asarray(parameters).reshape(2,3))]
    x=np.column_stack((a,b,np.ones(len(p.y))));normal=np.zeros((2,2));cross=np.zeros((2,2))
    for ix in p.segments:
        design=x[ix];coef=np.linalg.lstsq(design,p.y[ix],rcond=1e-8)[0]
        signal=np.column_stack((design[:,:8]@coef[:8],design[:,8:16]@coef[8:16]))
        df=2j*np.pi*p.centered[ix,None]*signal;ddot=1j*np.pi*p.centered[ix,None]**2*signal
        q,_=np.linalg.qr(design,mode='reduced');df-=q@(q.conj().T@df);ddot-=q@(q.conj().T@ddot)
        normal+=(df.conj().T@df).real;cross+=(df.conj().T@ddot).real
    mapping=np.linalg.solve(normal,cross)
    return dict(effective_time_s=float(p.t.mean())+mapping@np.ones(2),
        independent_component_rate_to_fitted_frequency_map_s=mapping)


def curvature_contrast(times,frequencies,covariances):
    t,f,c=(np.asarray(v,float) for v in (times,frequencies,covariances))
    if t.shape!=(3,2) or f.shape!=t.shape or c.shape!=(3,2,2) or not all(np.isfinite(v).all() for v in (t,f,c)) or np.any(np.diff(t,axis=0)<=0):
        raise ValueError('three ordered supported times and joint two-component covariances required')
    fraction=(t[1]-t[0])/(t[2]-t[0]);weights=np.stack((-(1-fraction),np.ones(2),-fraction))
    residual=np.sum(weights*f,axis=0);covariance=sum(np.diag(w)@cc@np.diag(w) for w,cc in zip(weights,c,strict=True))
    one=np.ones(2);precision=np.linalg.inv(covariance);variance=1/float(one@precision@one)
    common=float(variance*(one@precision@residual));contrast=np.array([1.,-1.])
    return dict(non_affine_CFO_contrast_hz=residual,covariance_hz2=covariance,
        common_contrast_hz=common,common_sigma_proxy_hz=float(np.sqrt(variance)),
        common_contrast_in_local_sigma=abs(common)/np.sqrt(variance),
        differential_contrast_hz=float(contrast@residual),
        differential_sigma_proxy_hz=float(np.sqrt(contrast@covariance@contrast)),
        conditional_local_proxies_not_calibrated_confidence=True)
