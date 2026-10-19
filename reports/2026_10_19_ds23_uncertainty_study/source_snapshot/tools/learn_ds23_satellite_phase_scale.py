"""Causal per-satellite phase scale from a population-centered scale mixture."""

import argparse
from pathlib import Path
import numpy as np

from learn_ds23_causal_phase_forecast import distribution_cost
from run_algo01_ds23_sample import read,write,sha


def softmax(logmass):
    mass=np.exp(logmass-np.max(logmass));return mass/mass.sum()


def posterior_multiplier(z,nu,strength):
    z=np.asarray(z,float)
    if z.ndim!=1 or not np.isfinite(z).all() or strength<0 or not np.isfinite(strength):
        raise ValueError('finite standardized innovations and nonnegative scale spread required')
    if strength==0 or not len(z):return 1.
    eta=np.linspace(-4,4,161);prior=softmax(-.5*(eta/strength)**2)
    tau=np.exp(eta)/np.sqrt(prior@np.exp(2*eta))
    cost=np.sum(distribution_cost(z[:,None],1.,tau[None,:],nu),axis=0)
    logprior=-.5*(eta/strength)**2
    posterior=softmax(logprior-.5*cost)
    return float(np.sqrt(posterior@(tau*tau)))


def errors(rows,parameters):
    sigma=np.array([r['predicted_sigma_s'] for r in rows])
    y=np.array([r['next_innovation_s'] for r in rows]);forecast=np.array([r['unit_forecast_s'] for r in rows])
    error=y-np.clip(parameters['shrinkage']*forecast,-np.minimum(15.,3*sigma),np.minimum(15.,3*sigma))
    return error,sigma*parameters['multiplier']


def fit_scales(rows,parameters,strength):
    if not rows:return {}
    e,s=errors(rows,parameters);groups={}
    for row,z in zip(rows,e/s,strict=True):groups.setdefault(str(row['norad']),[]).append(float(z))
    return {key:posterior_multiplier(z,parameters['nu'],strength) for key,z in groups.items()}


def cost(rows,parameters,multipliers):
    e,s=errors(rows,parameters)
    tau=np.array([multipliers.get(str(r['norad']),1.) for r in rows])
    return float(np.sum(distribution_cost(e,s,tau,parameters['nu'])))


def run(path):
    document=read(path);rows=document['transitions'];boundary=document['temporal_split_boundary_ns']
    prefix=[r for r in rows if r['validation_time_ns']<=boundary]
    validation=[r for r in rows if r['validation_time_ns']>boundary]
    parameters=document['prefix_distribution'];candidates=[]
    for strength in (0.,.25,.5,1.):
        scales=fit_scales(prefix,parameters,strength)
        candidates.append(dict(strength=strength,negative_twice_log_density=cost(validation,parameters,scales)))
    winner=min(candidates,key=lambda r:(r['negative_twice_log_density'],r['strength']))
    baseline=candidates[0]['negative_twice_log_density'];penalty=float(np.log(max(len(validation),1)))
    qualified=len(validation)>=30 and baseline-winner['negative_twice_log_density']>penalty
    strength=winner['strength'] if qualified else 0.
    full=fit_scales(rows,document['all_past_distribution'],strength)
    result=dict(case=document['case'],strictly_pre_RF=document['strictly_pre_RF'],GPS_or_radio_used=False,
        selected_strength=strength,qualified=qualified,validation_transitions=len(validation),prefix_candidates=candidates,
        required_gain=penalty,all_past_multipliers=full,training_and_prediction_model='moment-matched Student scale',
        population_prior_variance_multiplier_one=True,unseen_satellite_multiplier=1.,
        forecast_sha256=sha(path),source_sha256=sha(Path(__file__)))
    output=path.with_name(path.stem.replace('_forecast','_satellite_scale')+'.json');write(output,result)
    print(document['case'],'strength',strength,'qualified',qualified,'predictive gain',baseline-winner['negative_twice_log_density'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('forecast',type=Path)
    run(parser.parse_args().forecast)
