"""Conditional RF tests for periodic frequency ramps with resets.

Independent quartic trends absorb smooth orbit/receiver behavior. A single
Gaussian-regularized ramp amplitude is learned from training points only.
Predictive densities condition on a training-only noise estimate. They are
diagnostics, not calibrated clock or satellite-identity probabilities.
"""

import numpy as np


def ramp(times,origin_utc_ns,phase_s,period_s=15.):
    t=np.asarray(times,float)
    if t.ndim!=1 or not np.isfinite(t).all() or not np.isfinite([phase_s,period_s]).all() or period_s<=0:
        raise ValueError('finite one-dimensional times and positive period required')
    period_ns=int(round(period_s*1e9))
    if abs(period_ns/1e9-period_s)>1e-9:raise ValueError('nanosecond-representable period required')
    # Preserve the UTC fractional phase without casting an absolute epoch to float.
    return (((int(origin_utc_ns)%period_ns)/1e9+t-phase_s)%period_s)/period_s-.5


def fit(times,values,sigma_hz,origin_utc_ns,*,phase_s=None,period_s=15.,amplitude_sd_hz=300.):
    t,y=np.asarray(times,float),np.asarray(values,float)
    if t.ndim!=1 or y.shape!=t.shape or len(t)<10 or np.ptp(t)<=0 or not np.isfinite(np.r_[t,y]).all():
        raise ValueError('ten finite matching training points spanning time required')
    if sigma_hz<=0 or amplitude_sd_hz<=0 or not np.isfinite([sigma_hz,amplitude_sd_hz]).all():
        raise ValueError('finite positive noise and ramp-amplitude prior required')
    center=float(np.mean(t));scale=float(np.ptp(t)/2);v=np.polynomial.legendre.legvander((t-center)/scale,4)
    q,_=np.linalg.qr(v,mode='reduced');coefficient=np.linalg.lstsq(v,y,rcond=None)[0]
    residual=y-v@coefficient;variance=0.;alpha=0.;gain=0.;projected=np.zeros(5)
    if phase_s is not None:
        g=ramp(t,origin_utc_ns,phase_s,period_s);projected=np.linalg.lstsq(v,g,rcond=None)[0]
        u=g-q@(q.T@g);information=float(u@u);cross=float(u@residual)
        denominator=information+sigma_hz**2/amplitude_sd_hz**2
        alpha=cross/denominator;variance=sigma_hz**2/denominator
        gain=cross*cross/denominator/sigma_hz**2-np.log1p(information*amplitude_sd_hz**2/sigma_hz**2)
    return dict(center_s=center,scale_s=scale,polynomial_coefficients_hz=coefficient,
        polynomial_gram_inverse=np.linalg.inv(v.T@v),projected_ramp_coefficients=projected,
        amplitude_peak_to_peak_hz=float(alpha),amplitude_variance_hz2=float(variance),
        conditional_training_gain=float(gain),sigma_hz=float(sigma_hz),
        phase_s=phase_s,period_s=float(period_s),origin_utc_ns=int(origin_utc_ns))


def prediction(model,times):
    t=np.asarray(times,float);v=np.polynomial.legendre.legvander((t-model['center_s'])/model['scale_s'],4)
    mean=v@np.asarray(model['polynomial_coefficients_hz']);u=np.zeros(len(t))
    if model['phase_s'] is not None:
        u=ramp(t,model['origin_utc_ns'],model['phase_s'],model['period_s'])-v@np.asarray(model['projected_ramp_coefficients'])
        mean+=model['amplitude_peak_to_peak_hz']*u
    covariance=model['sigma_hz']**2*(np.eye(len(t))+v@np.asarray(model['polynomial_gram_inverse'])@v.T)
    covariance+=model['amplitude_variance_hz2']*np.outer(u,u)
    return mean,covariance


def predictive_score(mean,covariance,values):
    raw=np.asarray(values,float)-np.asarray(mean,float);c=np.asarray(covariance,float)
    if raw.ndim!=1 or c.shape!=(len(raw),len(raw)) or not np.isfinite(np.r_[raw,c.ravel()]).all():
        raise ValueError('finite matching prediction and covariance required')
    root=np.linalg.cholesky((c+c.T)/2);white=np.linalg.solve(root,raw)
    return float(white@white+2*np.log(np.diag(root)).sum()+len(raw)*np.log(2*np.pi))


def select(times,values,sigma_hz,origin_utc_ns,period_s=15.):
    baseline=fit(times,values,sigma_hz,origin_utc_ns)
    candidates=[fit(times,values,sigma_hz,origin_utc_ns,phase_s=phase,period_s=period_s)
                for phase in np.arange(30)*period_s/30]
    best=max(candidates,key=lambda r:r['conditional_training_gain'])
    best['phase_search_penalty']=float(2*np.log(30))
    best['selected_over_baseline']=bool(best['conditional_training_gain']>best['phase_search_penalty'])
    return best,baseline


def transfer(source_model,times,values,*,sigma_hz=None):
    """Train another RX's trend with ramp amplitude learned solely on source RX."""
    target=fit(times,values,source_model['sigma_hz'] if sigma_hz is None else sigma_hz,source_model['origin_utc_ns'],
               phase_s=source_model['phase_s'],period_s=source_model['period_s'])
    target['amplitude_peak_to_peak_hz']=source_model['amplitude_peak_to_peak_hz']
    target['amplitude_variance_hz2']=source_model['amplitude_variance_hz2']
    return target
