"""Refine only the causal phase-forecast gain; keep variance and tail degrees.

Historical revision scores are prediction proxies, not true-orbit errors.
No receiver measurement or geographic coordinate enters these functions.
"""

import numpy as np
from scipy.optimize import minimize_scalar

from ds23_causal_phase_location import fit_location, location_feature
from learn_ds23_causal_phase_forecast import distribution_cost


def arrays(rows, model, bias=None):
    sigma = np.array([r['predicted_sigma_s'] for r in rows])
    age = np.array([r['age_s'] for r in rows])
    correction = np.zeros(len(rows))
    if bias and bias.get('kind') is not None:
        correction = bias['coefficient']*location_feature(bias['kind'],sigma,age,model['multiplier'])
    return dict(target=np.array([r['next_innovation_s'] for r in rows]),
        unit=np.array([r['unit_forecast_s'] for r in rows]),sigma=sigma,
        correction=correction,limit=np.minimum(15.,3*sigma))


def cost(a, model, rho):
    ordinary = np.clip(rho*a['unit'],-a['limit'],a['limit'])
    mean = np.clip(ordinary+a['correction'],-a['limit'],a['limit'])
    return float(distribution_cost(a['target']-mean,a['sigma'],model['multiplier'],model['nu']).sum())


def fit_gain(rows, model, bias=None, continuous=True):
    if not rows:
        raise ValueError('nonempty historical phase transitions required')
    a = arrays(rows,model,bias)
    grid = np.linspace(0,1,33 if continuous else 5)
    values = np.array([cost(a,model,float(rho)) for rho in grid])
    candidates = [(float(v),float(r)) for v,r in zip(values,grid,strict=True)]
    if continuous:
        brackets=[]
        if values[0]<=values[1]:brackets.append((grid[0],grid[1]))
        if values[-1]<=values[-2]:brackets.append((grid[-2],grid[-1]))
        for k in range(1,len(grid)-1):
            if values[k]<=values[k-1] and values[k]<=values[k+1]:
                brackets.append((grid[k-1],grid[k+1]))
        for bounds in brackets:
            fit = minimize_scalar(lambda rho:cost(a,model,rho),
                bounds=bounds,method='bounded',options=dict(xatol=1e-8))
            candidates.append((float(fit.fun),float(fit.x)))
    value,rho = min(candidates)
    return dict(gain=rho,cost=value,continuous=continuous,bias=bias,
        original_coarse_grid=[0.,.25,.5,.75,1.],variance_and_tail_degrees_unchanged=True)


def qualify(forecast, full_model, bias_enabled, full_bias):
    rows = forecast['transitions']
    boundary = forecast['temporal_split_boundary_ns']
    train = [r for r in rows if r['validation_time_ns']<=boundary and r['norad']%5!=0]
    future = [r for r in rows if r['validation_time_ns']>boundary]
    disjoint = [r for r in future if r['norad']%5==0]
    if min(len(train),len(future),len(disjoint))<30:
        return dict(qualified=False,reason='insufficient historical temporal/satellite validation')
    prefix_model = forecast['prefix_distribution']
    prefix_bias = fit_location(train,prefix_model) if bias_enabled else None
    coarse = fit_gain(train,prefix_model,prefix_bias,False)
    fine = fit_gain(train,prefix_model,prefix_bias,True)
    scores = {}
    for name,subset in (('future',future),('disjoint_future',disjoint)):
        a = arrays(subset,prefix_model,prefix_bias)
        scores[name] = dict(count=len(subset),coarse_cost=cost(a,prefix_model,coarse['gain']),
            fine_cost=cost(a,prefix_model,fine['gain']))
        scores[name]['gain'] = scores[name]['coarse_cost']-scores[name]['fine_cost']
    penalty = float(2*np.log(33))
    qualified = bool(all(r['gain']>penalty for r in scores.values()))
    all_coarse = fit_gain(rows,full_model,full_bias,False)
    all_fine = fit_gain(rows,full_model,full_bias,True)
    return dict(qualified=qualified,prefix_coarse=coarse,prefix_fine=fine,validation=scores,
        all_past_coarse=all_coarse,all_past_fine=all_fine,penalty=penalty,
        train_count=len(train),temporal_boundary_ns=boundary,
        gain_fit_excludes_held_satellites=True,
        baseline_prefix_variance_and_tail_model_conditioned_not_relearned=True,
        TLE_updates_correlated_proxies_not_orbit_truth=True,
        coefficient_inputs_are_pre_RF_TLE_transitions=True)
