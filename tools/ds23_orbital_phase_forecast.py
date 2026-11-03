"""Causal phase-mean harmonics with no observer position or RF selection."""

import numpy as np
from scipy.optimize import minimize
from sgp4.api import Satrec

from learn_ds23_causal_phase_forecast import distribution_cost
from leo.sky.frames import julian_day_from_utc_ns


def argument_latitude(position, velocity):
    r, v = np.asarray(position, float), np.asarray(velocity, float)
    if r.shape != (3,) or v.shape != (3,) or not np.isfinite(r).all() or not np.isfinite(v).all():
        raise ValueError('finite three-dimensional orbital state required')
    h = np.cross(r, v); node = np.cross([0., 0., 1.], h)
    if np.linalg.norm(h) <= 0 or np.linalg.norm(node) <= 1e-10*np.linalg.norm(h):
        raise ValueError('non-equatorial orbital plane required')
    node /= np.linalg.norm(node); transverse = np.cross(h/np.linalg.norm(h), node)
    return float(np.arctan2(r@transverse, r@node))


def tle_argument_latitude(lines, target_ns):
    jd, fr = julian_day_from_utc_ns(np.array([target_ns]))
    status, r, v = Satrec.twoline2rv(*lines).sgp4(float(jd[0]), float(fr[0]))
    if status:
        raise ValueError('causal TLE propagation failed')
    return argument_latitude(r, v)


def harmonic_features(angles, width):
    if width not in (0, 2, 4):
        raise ValueError('zero, one or two orbital harmonics required')
    a = np.asarray(angles, float)
    if not np.isfinite(a).all():
        raise ValueError('finite orbital angles required')
    return np.column_stack([f(k*a) for k in range(1, width//2+1) for f in (np.sin, np.cos)]) if width else np.zeros((len(a),0))


def prediction(rows, model, beta):
    sigma = np.array([r['predicted_sigma_s'] for r in rows])
    ordinary = model['shrinkage']*np.array([r['unit_forecast_s'] for r in rows])
    features = harmonic_features([r['argument_latitude_rad'] for r in rows],len(beta))
    correction = sigma*model['multiplier']*(features@np.asarray(beta))
    limit = np.minimum(15., 3*sigma)
    return np.clip(ordinary+correction, -limit, limit)


def cost(rows, model, beta):
    target = np.array([r['next_innovation_s'] for r in rows])
    sigma = np.array([r['predicted_sigma_s'] for r in rows])
    return float(distribution_cost(target-prediction(rows,model,beta),sigma,model['multiplier'],model['nu']).sum())


def fit_model(rows, model, widths=(0,2,4)):
    choices=[]
    for width in widths:
        if width:
            result=minimize(lambda b:cost(rows,model,b)+float(b@b),np.zeros(width),
                            method='L-BFGS-B',bounds=[(-3.,3.)]*width,
                            options=dict(maxiter=100,ftol=1e-10))
            beta=np.asarray(result.x)
        else:
            beta=np.zeros(0)
        loss=cost(rows,model,beta)
        penalty=width*np.log(max(len(rows),1))+float(beta@beta)
        choices.append(dict(width=width,beta=beta,cost=loss,penalty=penalty,
                            criterion=loss+penalty))
    return dict(min(choices,key=lambda v:v['criterion']),choices=choices)


def qualify(rows,boundary,prefix_model,full_model):
    # The correction never sees held-satellite innovation labels in training.
    train=[r for r in rows if r['validation_time_ns']<=boundary and r['norad']%5!=0]
    future=[r for r in rows if r['validation_time_ns']>boundary]
    disjoint=[r for r in future if r['norad']%5==0]
    if len(train)<30 or len(future)<30 or len(disjoint)<30:
        return dict(qualified=False,beta=[],reason='insufficient causal validation support',
                    training_count=len(train),future_count=len(future),disjoint_future_count=len(disjoint))
    prefix=fit_model(train,prefix_model);beta=prefix['beta'];width=len(beta)
    future_gain=cost(future,prefix_model,[])-cost(future,prefix_model,beta)
    disjoint_gain=cost(disjoint,prefix_model,[])-cost(disjoint,prefix_model,beta)
    qualifies=width>0 and future_gain>width*np.log(len(future)) and disjoint_gain>width*np.log(len(disjoint))
    full=fit_model(rows,full_model,widths=(width,)) if qualifies else None
    return dict(qualified=bool(qualifies),beta=full['beta'] if qualifies else [],
                prefix=prefix,all_past=full,training_count=len(train),future_count=len(future),
                disjoint_future_count=len(disjoint),future_density_gain=future_gain,
                disjoint_future_density_gain=disjoint_gain,
                additional_density_parameters=width,
                correction_satellite_disjoint_and_chronologically_future_validation=True,
                baseline_density_hyperparameters_frozen_from_original_causal_learner=True)
