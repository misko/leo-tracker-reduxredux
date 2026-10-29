"""Alias-aware curve discovery diagnostics, never association acceptance."""
import numpy as np
from .retained_track_likelihood import PERIOD


def profile_rate(observed,predicted,times,*,rate_sigma_hz_s=0.,noise_hz=150.,bias_sigma_hz=1000.):
    y=np.asarray(observed,float);f=np.atleast_2d(predicted);t=np.asarray(times,float)
    if y.ndim!=1 or t.shape!=y.shape or f.shape[1]!=len(y) or len(y)<3:
        raise ValueError('matching curve and predictions required')
    if not all(np.isfinite(v).all() for v in (y,f,t)) or np.ptp(t)<=0:
        raise ValueError('finite curve with positive duration required')
    if rate_sigma_hz_s<0 or noise_hz<=0 or bias_sigma_hz<=0:raise ValueError('valid noise and prior scales required')
    x=t-t.mean();raw=y-f;alias=np.rint(-raw.mean(axis=1)/PERIOD);raw=raw+alias[:,None]*PERIOD
    bias=raw.sum(axis=1)/(len(t)+noise_hz**2/bias_sigma_hz**2)
    rate=raw@x/(x@x+noise_hz**2/rate_sigma_hz_s**2) if rate_sigma_hz_s else np.zeros(len(f))
    residual=raw-bias[:,None]-rate[:,None]*x
    cost=np.sum((residual/noise_hz)**2,axis=1)+(bias/bias_sigma_hz)**2
    cost+=np.log1p(len(t)*bias_sigma_hz**2/noise_hz**2)
    if rate_sigma_hz_s:
        cost+=(rate/rate_sigma_hz_s)**2+np.log1p((x@x)*rate_sigma_hz_s**2/noise_hz**2)
    return dict(alias=alias,bias_hz=bias,rate_hz_s=rate,residual_hz=residual,
                rms_hz=np.sqrt(np.mean(residual**2,axis=1)),cost=cost)


def shortlist(observed,times,rf_scale,frequency,elevation,knots,phases,*,top=5,rate_sigma_hz_s=0.,bias_sigma_hz=1000.):
    """Rank every bank satellite over a coarse phase grid at one position.

    Frequency/elevation have shape (phase,satellite,time). Interpolation is
    solely nomination; all retained hypotheses require exact full-point checks.
    """
    t=np.asarray(times);grid=np.asarray(knots);f=np.asarray(frequency);e=np.asarray(elevation)
    if f.shape!=e.shape or f.ndim!=3 or f.shape[0]!=len(phases) or f.shape[2]!=len(grid):raise ValueError('matching phase/satellite/time grids required')
    if np.any(t<grid[0]) or np.any(t>grid[-1]):raise ValueError('no time extrapolation')
    idx=np.clip(np.searchsorted(grid,t,side='right')-1,0,len(grid)-2);frac=(t-grid[idx])/(grid[idx+1]-grid[idx])
    pred=f[...,idx]*(1-frac)+f[...,idx+1]*frac
    elev=e[...,idx]*(1-frac)+e[...,idx+1]*frac
    result=profile_rate(observed,rf_scale*pred.reshape(-1,len(t)),t,rate_sigma_hz_s=rate_sigma_hz_s,bias_sigma_hz=bias_sigma_hz)
    score=np.where(elev.min(axis=-1).reshape(-1)>=0,result['cost'],np.inf).reshape(f.shape[:2])
    best_phase=score.argmin(axis=0);best=score[best_phase,np.arange(f.shape[1])]
    return [dict(candidate_index=int(j),phase_s=float(phases[best_phase[j]]),cost=float(best[j]))
            for j in np.argsort(best)[:top] if np.isfinite(best[j])]
