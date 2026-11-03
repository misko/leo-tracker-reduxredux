"""Use linear curves only through prediction from the curved-data posterior.

No linear observation enters calibration normal equations. The predictive
Gaussian approximates the existing hierarchical posterior at its fitted Gamma
precisions; shared uncertainty is kept across all added curves.
"""

from types import SimpleNamespace
import numpy as np
from ds23_frozen_precision import conditional_gaussian
from ds23_height_problem import geometry_features
from leo.analysis.research.retained_track_likelihood import PERIOD


def predictive_residual(raw,design,curved_gram,sigma,groups,bias_sigma=300.):
    y,u=np.asarray(raw,float),np.asarray(design,float)
    gram=np.asarray(curved_gram,float);g=np.asarray(groups)
    if gram.shape!=(u.shape[1],u.shape[1]) or g.shape!=y.shape or not np.issubdtype(g.dtype,np.integer) or np.any(g<0):
        raise ValueError('matching curved precision and integer new-curve groups required')
    root=np.linalg.cholesky(gram)
    # If A=LL', theta uncertainty is L'^-1 z, z~N(0,I).
    uncertainty=np.linalg.solve(root,u.T).T
    biases=np.zeros((len(y),int(g.max())+1));biases[np.arange(len(y)),g]=bias_sigma
    features=np.column_stack((uncertainty,biases))
    result=conditional_gaussian(y,features,np.asarray(sigma,float),np.ones(len(y)),np.ones(len(y)),np.ones(features.shape[1]),1.)
    return result


def linear_geometry(p,entries):
    scan=p.scan;members=[e['track_index'] for e in entries]
    counts=[len(scan.tracks[i]['times']) for i in members];n=sum(counts)
    boundaries=np.r_[0,np.cumsum(counts)]
    slices=[slice(a,b) for a,b in zip(boundaries[:-1],boundaries[1:],strict=True)]
    times=np.concatenate([scan.tracks[i]['times'] for i in members])
    labels=np.repeat([p.labels.index(e['candidate_index']) for e in entries],counts)
    q=np.concatenate([np.full(count,scan.tracks[i]['rf_hz']/11.5e9) for i,count in zip(members,counts,strict=True)])
    hardware=np.zeros((n,p.hardware.shape[1]));smooth=np.zeros((n,p.smooth.shape[1]));width=smooth.shape[1]//2
    for i,sl in zip(members,slices,strict=True):
        t=scan.tracks[i];rx=t['receiver']-1;band=int(t['channel']>4)
        hardware[sl,2*rx+band]=PERIOD/np.sqrt(12)
        hardware[sl,4+2*rx]=t['times']-150
        hardware[sl,5+2*rx]=(t['times']-150)*(-1 if band==0 else 1)*.5
        if p.fitted_c:hardware[sl,8]=(t['rf_hz']/1e9-11.5)*200000
        smooth[sl,rx*width:(rx+1)*width]=q[sl,None]*scan.rx_basis[i]
    fields=dict(vars(p));fields.update(flat_times=times,flat_labels=labels,q=q,hardware=hardware,smooth=smooth,
        constants=np.zeros((n,len(p.members))))
    view=SimpleNamespace(**fields)
    values=np.concatenate([scan.tracks[i]['values']+e['alias']*PERIOD for i,e in zip(members,entries,strict=True)])
    ids=[o for i in members for o in scan.tracks[i]['observation_ids']]
    meta=scan.fixed_window_noise;by_id=meta['per_observation_noise_sigma_hz']
    sigma=np.array([by_id[o] if meta['extra_parameter_BIC_gain']>0 else scan.radio_sigma_hz for o in ids])
    return view,values,sigma,np.repeat(np.arange(len(entries)),counts),slices


def attach_predictive_linear(p,entries,powers):
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    curved_calculate=p.calculate
    def calculate(position):
        c=curved_calculate(position)
        g=p.noise_groups[p.keep]
        w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        geometry=geometry_features(view,position,0.)
        mean=view.q*geometry['intercept']+geometry['features']@c['coefficient']
        # Unseen Gamma(2,2) noise: E[1/tau]=2, not fitted from linear points.
        prediction=predictive_residual(values-mean,geometry['features'],gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['linear_predictive_objective']=prediction['objective']
        c['negative_twice_elbo']+=prediction['objective']
        c['normalization_constant']+=prediction['normalization_constant']
        c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-mean
        c['linear_elevation']=geometry['elevation']
        c['linear_calibration_coefficient_unchanged']=True
        return c
    p.calculate=calculate;p.linear_entries=entries;p.linear_slices=slices
    p.curved_calculate=curved_calculate
    return p
