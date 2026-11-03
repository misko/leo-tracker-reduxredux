"""Noise-aware conditional prediction of shared, freely changing TX frame gains.

Both receiver gains have complex Gaussian extraction noise. The common complex
transmitter gain is integrated with a flat prior, yielding an errors-in-variables
conditional density. No individual-transmitter phase continuity is assumed.
Training-only discrepancy variance absorbs departures from a fixed channel ratio.
"""

import numpy as np
from scipy.optimize import minimize


def validate(times,first,second,var_first,var_second):
    t,a,b,va,vb=map(np.asarray,(times,first,second,var_first,var_second))
    if t.ndim!=1 or min(len(t),len(a),len(b),len(va),len(vb))<4 or any(v.shape!=t.shape for v in [a,b,va,vb]):
        raise ValueError('four aligned paired receiver gains required')
    if not all(np.isfinite(v).all() for v in [t,a,b,va,vb]) or np.any(va<=0) or np.any(vb<=0) or np.any(np.diff(t)<=0):
        raise ValueError('finite ordered gains and positive extraction variances required')
    return t.astype(float),a.astype(complex),b.astype(complex),va.astype(float),vb.astype(float)


def loss(parameters,t,a,b,va,vb,*,shared,prior=True):
    re,im,frequency,log_discrepancy=np.asarray(parameters,float);ratio=re+1j*im
    predictor=a if shared else np.ones(len(a),complex)
    variance=vb+(abs(ratio)**2*va if shared else 0.)+np.exp(log_discrepancy)
    residual=b-ratio*np.exp(2j*np.pi*frequency*t)*predictor
    value=float(np.sum(np.log(np.pi*variance)+abs(residual)**2/variance))
    if prior:value+=(frequency/100.)**2
    return value


def fit(times,first,second,var_first,var_second,*,shared=True):
    t,a,b,va,vb=validate(times,first,second,var_first,var_second);center=float(t.mean());t=t-center
    norm_a=max(float(np.sqrt(np.mean(abs(a)**2))),1e-12);norm_b=max(float(np.sqrt(np.mean(abs(b)**2))),1e-12)
    a,b,va,vb=a/norm_a,b/norm_b,va/norm_a**2,vb/norm_b**2
    predictor=a if shared else np.ones(len(a),complex)
    frequencies=np.linspace(-375.,375.,751);weights=1/(va+vb+.1) if shared else 1/(vb+.1)
    cross=np.exp(-2j*np.pi*frequencies[:,None]*t)@(weights*b*predictor.conj())
    coefficient=cross/np.sum(weights*abs(predictor)**2)
    proposals=[]
    for k in np.argsort(abs(cross))[::-1]:
        if any(abs(frequencies[k]-frequencies[j])<20 for j in proposals):continue
        proposals.append(int(k))
        if len(proposals)==3:break
    trials=[]
    for k in proposals:
        initial=np.array([coefficient[k].real,coefficient[k].imag,frequencies[k],np.log(.1)])
        result=minimize(lambda x:loss(x,t,a,b,va,vb,shared=shared),initial,method='L-BFGS-B',
            bounds=[(-3,3),(-3,3),(-375,375),(-16,3)],options=dict(maxiter=120,ftol=1e-10))
        if np.isfinite(result.fun):trials.append(result)
    if not trials:raise ValueError('no finite paired-gain frequency fit')
    best=min(trials,key=lambda r:r.fun)
    return dict(parameters=best.x,penalized_training_NLL=float(best.fun),converged=bool(best.success),
        shared_transmitter_gain=shared,time_center_s=center,first_scale=norm_a,second_scale=norm_b,
        frequency_correction_mod750_hz=float(best.x[2]),extra_variance=float(np.exp(best.x[3])),
        boundary=bool(abs(best.x[2])>=374.5 or max(abs(best.x[:2]))>=2.99),
        frequency_ambiguity_period_hz=750.,conditional_extraction_noise_not_calibrated_total_error=True)


def predict(model,times,first,second,var_first,var_second):
    t,a,b,va,vb=validate(times,first,second,var_first,var_second)
    a,b,va,vb=a/model['first_scale'],b/model['second_scale'],va/model['first_scale']**2,vb/model['second_scale']**2
    value=loss(model['parameters'],t-model['time_center_s'],a,b,va,vb,shared=model['shared_transmitter_gain'],prior=False)
    # Restore the target gain's complex-density scale for matched comparisons.
    return float(value+2*len(t)*np.log(model['second_scale']))
