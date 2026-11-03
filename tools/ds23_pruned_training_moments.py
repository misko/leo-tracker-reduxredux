"""Equivalent held-family training moments, eliminating unobserved columns.

Only singleton Student prior groups are supported. Unobserved Gaussian modes
retain unit precision; unobserved Student coordinates retain their original
mean-field expected precision. This adapter returns moments, never an ELBO.
"""

import numpy as np
from dsx01_hierarchical_bound import hierarchical_bound
from ds23_height_problem import geometry_features
from ds23_frequency_events import make_event_problem


def pruned_moments(raw,features,sigma,groups,powers,prior_groups,nu,scales):
    u=np.asarray(features,float);prior=np.asarray(prior_groups,int);scale=np.asarray(scales,float)
    active=np.flatnonzero(np.any(u!=0,axis=0));student=prior>=0
    if np.any(np.unique(prior[student],return_counts=True)[1]!=1):
        raise ValueError('singleton Student coordinates required for exact moment pruning')
    result=hierarchical_bound(raw,u[:,active],sigma,groups,powers=powers,
        prior_groups=prior[active],prior_nu=nu)
    coefficient=np.zeros(u.shape[1]);coefficient[active]=result['coefficient']*scale[active]
    precision=np.ones(u.shape[1]);precision[student]=nu/(nu-2)
    precision[active]=result['coefficient_prior_precision'];precision/=scale**2
    return dict(coefficient=coefficient,coefficient_prior_precision=precision,
        noise_precision=result['noise_precision'],active_nuisance_columns=len(active),
        original_nuisance_columns=u.shape[1],no_ELBO_returned_from_moment_adapter=True)


def make_training_problem(scan,node,keep,arm,reference,powers,means,model):
    p=make_event_problem(scan,node,keep,arm,reference,powers,means,model,[])
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    prior=np.full(width,-1,int)
    if model['nu'] is not None:prior[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    def calculate(position):
        geometry=geometry_features(p,position,0.);features=geometry['features']
        raw=p.values-p.q*geometry['intercept']-features@mean;present=np.unique(p.noise_groups[keep])
        result=pruned_moments(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            np.asarray(powers)[present],prior,model['nu'] or 4.,scale)
        result['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=result['noise_precision'];result['noise_precision']=precision
        result['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@result['coefficient']
        geometry.update(result);return geometry
    p.calculate=calculate;return p
