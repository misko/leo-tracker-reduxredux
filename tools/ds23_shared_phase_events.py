"""Causal diagnostic for shared phase errors within TLE publication events.

An exchangeable symmetric covariance root preserves marginal variance and
satellite permutation symmetry. Independent Student latent coordinates give
an explicit density; this is not a multivariate Student distribution.
"""

import numpy as np
from learn_ds23_causal_phase_forecast import distribution_cost

RHOS=(0.,.01,.03,.1,.2,.4,.6,.8)


def whiten(z,rho):
    z=np.asarray(z,float)
    if z.ndim!=1 or not len(z) or not 0<=rho<1 or not np.isfinite(z).all():
        raise ValueError("finite nonempty phase vector and correlation in [0,1) required")
    transverse=np.sqrt(1-rho);common=np.sqrt(1+(len(z)-1)*rho)
    result=(z-z.mean())/transverse+z.mean()/common
    logdet=(len(z)-1)*np.log1p(-rho)+np.log1p((len(z)-1)*rho)
    return result,float(logdet)


def event_cost(z,rho,nu):
    latent,logdet=whiten(z,rho)
    return float(distribution_cost(latent,np.ones(len(latent)),1.,nu).sum()+logdet)


def fit(events,nu):
    count=sum(len(e) for e in events)
    candidates=[dict(rho=rho,cost=sum(event_cost(e,rho,nu) for e in events)) for rho in RHOS]
    chosen=min(candidates,key=lambda r:r["cost"]+(np.log(max(count,1)) if r["rho"] else 0.))
    return dict(rho=chosen["rho"],candidates=candidates,events=len(events),satellite_versions=count)


def standardized(rows,model):
    sigma=np.array([r["predicted_sigma_s"] for r in rows]);limit=np.minimum(15.,3*sigma)
    prediction=np.clip(model["shrinkage"]*np.array([r["unit_forecast_s"] for r in rows]),-limit,limit)
    return (np.array([r["next_innovation_s"] for r in rows])-prediction)/(sigma*model["multiplier"])


def qualify(groups,boundary,prefix_model,full_model):
    # No forecast-element publication event may straddle train and test.
    # Training labels must already have arrived by the temporal boundary.
    train=[standardized([r for r in rows if r["validation_time_ns"]<=boundary],prefix_model)
           for key,rows in groups.items() if key<=boundary]
    train=[z for z in train if len(z)>=5]
    test=[standardized(rows,prefix_model) for key,rows in groups.items() if key>boundary and len(rows)>=5]
    full=[standardized(rows,full_model) for rows in groups.values() if len(rows)>=5]
    if len(train)<3 or len(test)<2:return dict(qualified=False,reason="fewer than three training or two unseen publication events")
    prefix=fit(train,prefix_model["nu"]);all_past=fit(full,full_model["nu"])
    gain=sum(event_cost(z,0.,prefix_model["nu"])-event_cost(z,prefix["rho"],prefix_model["nu"]) for z in test)
    penalty=np.log(sum(len(z) for z in test))
    return dict(qualified=bool(prefix["rho"] and gain>penalty),rho=all_past["rho"] if prefix["rho"] and gain>penalty else 0.,
        validation_gain=float(gain),penalty=float(penalty),prefix=prefix,all_past=all_past,
        validation_events=len(test),publication_events_are_disjoint_between_training_and_validation=True,
        baseline_nu_marginal_scales_and_mean_preserved=True,
        small_number_of_publication_events_limits_generalization_evidence=True)
