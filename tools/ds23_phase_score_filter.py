"""Phase-prequential fitting and an optional causal acceleration-mean term.

The conditional phase score is proper; it conditions on earlier phase/rate
observations. This changes empirical hyperparameter selection, not the base
Normal-Gamma filter. Model selection is done before any receiver-position fit.
"""

import numpy as np
from scipy.optimize import minimize

from ds23_tle_state_filter import filter_histories,predict_state


def filter_with_mean(data,parameters):
    rp,rv,sqrtq,acceleration=parameters
    adjusted=dict(data);y=data['observations'].copy();t=data['times']
    y[:,:,0]-=.5*acceleration*t*t;y[:,:,1]-=acceleration*t
    adjusted['observations']=y
    result=filter_histories(adjusted,[rp,rv,sqrtq])
    result['predicted_mean']+=.5*acceleration*t*t
    result['acceleration_mean_s_per_hour2']=float(acceleration)
    return result


def predict_with_mean(result,target_hours):
    prediction=predict_state(result,target_hours)
    prediction['mean']+=.5*result['acceleration_mean_s_per_hour2']*np.asarray(target_hours)**2
    return prediction


def fit(data,mask,measurement=True):
    count=int(np.sum(mask))
    if count<30:raise ValueError('thirty phase-scoring transitions required')
    choices=[]
    for acceleration in (False,True):
        bounds=list(np.log([[.01,3.],[.001,1.],[.0003,1.]])) if measurement else [np.log([.0003,1.])]
        if acceleration:bounds.append((-5.,5.))
        starts=[(.1,.03,.01),(.3,.1,.03),(.03,.01,.1),(1.,.3,.3)] if measurement else [(0.,0.,.01),(0.,0.,.1)]
        def unpack(x):
            noise=np.exp(x[:3]).tolist() if measurement else [0.,0.,float(np.exp(x[0]))]
            return noise+[float(x[-1]*.02) if acceleration else 0.]
        def objective(x):
            predicted=filter_with_mean(data,unpack(x))
            return float(predicted['phase_cost'][mask].sum()+(x[-1]**2 if acceleration else 0.))
        fitted=[]
        for start in starts:
            initial=np.log(start if measurement else [start[-1]]).tolist()
            if acceleration:initial.append(0.)
            result=minimize(objective,initial,method='L-BFGS-B',bounds=bounds,
                options=dict(maxiter=120,ftol=1e-10))
            if result.success:
                parameters=unpack(result.x)
                score=float(filter_with_mean(data,parameters)['phase_cost'][mask].sum())
                penalty=(parameters[-1]/.02)**2
                fitted.append(dict(parameters=parameters,phase_cost=score,mean_prior_penalty=penalty,
                    criterion=score+penalty+len(initial)*np.log(count),
                    mean_acceleration_enabled=acceleration,converged=True))
        if not fitted:raise ValueError('phase-score filter optimizers did not converge')
        choices.append(min(fitted,key=lambda r:r['criterion']))
    return dict(min(choices,key=lambda r:r['criterion']),choices=choices,count=count,
        criterion='phase-prequential NLL + Gaussian mean prior + k log N',
        measurement_noise_enabled=measurement)
