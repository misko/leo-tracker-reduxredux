"""Exploratory shared pulse estimated from other curves, never target values.

This diagnoses abrupt residual structure; it is not an association policy.
Boundary search is penalized but does not provide calibrated event confidence.
"""
import numpy as np


def fit_pulse(witnesses, window, *, step_s=.5, minimum_s=2., maximum_s=12.):
    if not 0<step_s<=minimum_s<=maximum_s:raise ValueError('invalid pulse grid')
    arrays=[];components=[]
    for w in witnesses:
        t=np.asarray(w['times_s'],float);r=np.asarray(w['residual_hz'],float);m=(t>=window[0])&(t<=window[1])
        if m.sum()<8:continue
        arrays.append((t[m],r[m]));components.append(w['component'])
    if len(arrays)<2:raise ValueError('two witness curves required')
    t=np.concatenate([a for a,b in arrays]);y=np.concatenate([b for a,b in arrays]);n=len(t)
    groups=np.repeat(np.arange(len(arrays)),[len(a) for a,b in arrays])
    centered=y.copy()
    for k in range(len(arrays)):centered[groups==k]-=y[groups==k].mean()
    baseline=float(centered@centered);best=None
    for start in np.arange(np.ceil(window[0]/step_s)*step_s,window[1]-minimum_s+1e-8,step_s):
        for duration in np.arange(minimum_s,maximum_s+1e-8,step_s):
            end=start+duration
            if end>window[1]:continue
            indicator=((t>=start)&(t<end)).astype(float)
            # Require inside/outside evidence in multiple curves. This does
            # not establish precision of either event boundary.
            support=[k for k in range(len(arrays)) if np.sum(indicator[groups==k])>=3 and np.sum(1-indicator[groups==k])>=3]
            if len(support)<2 or indicator.sum()<8:continue
            z=indicator.copy()
            for k in range(len(arrays)):z[groups==k]-=indicator[groups==k].mean()
            amp=float(z@centered/(z@z+(75./150.)**2))
            remaining=centered-z*amp
            objective=float(remaining@remaining+(75./150.)**2*amp**2)
            if best is None or objective<best['objective']:
                best=dict(start_s=float(start),end_s=float(end),amplitude_hz=amp,objective=objective,
                    witness_points=n,witness_components=components,supported_components=[components[k] for k in support],
                    baseline_RMS_hz=float(np.sqrt(baseline/n)),after_RMS_hz=float(np.sqrt(remaining@remaining/n)),
                    penalized_gain=float((baseline-objective)/75.**2-3*np.log(n)),
                    amplitude_prior_sigma_hz=150,assumed_noise_hz=75,
                    model='shared additive Hz pulse + one constant per witness',
                    diagnostic_only=True,uncertainty_in_event_boundaries_not_integrated=True)
    if best is None:raise ValueError('no pulse with independent curve support')
    return best


def pulse_prediction(times, result):
    t=np.asarray(times)
    return result['amplitude_hz']*((t>=result['start_s'])&(t<result['end_s']))
