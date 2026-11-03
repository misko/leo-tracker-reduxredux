"""Variance-preserving two-piece phase priors; causal historical qualification.

The underlying symmetric law is the existing unit-variance Student (or normal).
The mode stays at the ordinary forecast; asymmetry is an independent parameter.
"""

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammaln

from learn_ds23_causal_phase_forecast import distribution_cost
from ds23_causal_phase_location import predict as ordinary_prediction, fit_location, cost as location_cost


def side_scales(kappa, nu):
    if not np.isfinite(kappa) or abs(kappa)>3 or (nu is not None and (not np.isfinite(nu) or nu<=2)):
        raise ValueError('finite bounded asymmetry and a finite-variance base law required')
    absolute_mean = (np.sqrt(2/np.pi) if nu is None else
        np.exp(.5*np.log(nu-2)+gammaln((nu-1)/2)-.5*np.log(np.pi)-gammaln(nu/2)))
    left,right=np.exp(kappa),np.exp(-kappa)
    variance=left*left-left*right+right*right-absolute_mean**2*(right-left)**2
    scale=np.sqrt(variance)
    return float(left/scale),float(right/scale),float((right-left)*absolute_mean/scale)


def density_cost(errors,sigma,multiplier,nu,kappa):
    errors=np.asarray(errors,float)
    left,right,_=side_scales(kappa,nu)
    side=np.where(errors<0,left,right)
    return distribution_cost(errors/side,sigma,multiplier,nu)+2*np.log((left+right)/2)


def cost(rows,model,kappa):
    target=np.array([r['next_innovation_s'] for r in rows])
    scale=np.array([r['predicted_sigma_s'] for r in rows])
    return float(density_cost(target-ordinary_prediction(rows,model),scale,model['multiplier'],model['nu'],kappa).sum())


def fit_skew(rows,model):
    fitted=minimize_scalar(lambda k:cost(rows,model,k)+k*k,bounds=(-1.25,1.25),method='bounded',options=dict(xatol=1e-7))
    k=float(fitted.x);baseline=cost(rows,model,0.)
    improvement=baseline-cost(rows,model,k)
    penalty=np.log(max(len(rows),1))+2*np.log(2)+k*k
    return dict(kappa=k if improvement>penalty else 0.,raw_kappa=k,
                density_gain=improvement,penalty=penalty,count=len(rows))


def qualify(rows,boundary,prefix_model,full_model):
    train=[r for r in rows if r['validation_time_ns']<=boundary and r['norad']%5!=0]
    future=[r for r in rows if r['validation_time_ns']>boundary]
    disjoint=[r for r in future if r['norad']%5==0]
    if min(map(len,(train,future,disjoint)))<30:
        return dict(qualified=False,kappa=0.,reason='insufficient causal temporal and satellite-disjoint support')
    prefix=fit_skew(train,prefix_model)
    location=fit_location(train,prefix_model)
    comparisons={}
    for label,test in [('future',future),('disjoint',disjoint)]:
        new=cost(test,prefix_model,prefix['kappa'])
        baseline=cost(test,prefix_model,0.)
        shifted=location_cost(test,prefix_model,location['kind'],location['coefficient'])
        comparisons[label]=dict(count=len(test),gain_vs_original=baseline-new,gain_vs_location=shifted-new,
            required_gain=float(np.log(len(test))+2*np.log(2)))
    qualifies=bool(prefix['kappa'] and all(
        r['gain_vs_original']>r['required_gain'] and r['gain_vs_location']>r['required_gain'] for r in comparisons.values()))
    full=fit_skew(rows,full_model) if qualifies else None
    qualifies=bool(qualifies and full['kappa'])
    return dict(qualified=qualifies,kappa=full['kappa'] if qualifies else 0.,prefix=prefix,
        prefix_location=location,all_past=full,validation=comparisons,
        mode_and_marginal_variance_preserved=True,asymmetry_may_change_the_prior_mean=True,
        actual_third_moment_need_not_exist_for_nu3=True)
