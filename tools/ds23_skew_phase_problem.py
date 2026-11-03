"""Frozen RF geometry with one pre-scan-qualified asymmetric phase law."""

import numpy as np

from ds23_skew_bound import skew_bound
from ds23_predictive_linear import linear_geometry,predictive_residual,attach_predictive_linear
from ds23_height_problem import geometry_features
from dsx01_joint_marginal import JointMarginal
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def make_skew_problem(scan,node,keep,arm,reference,powers,means,model,kappa):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    p.skew_kappa=kappa;p.events=[]
    if kappa==0:return p
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    scale=np.ones(width);scale[-len(p.members):]=.3
    phase_indices=np.arange(begin,begin+len(p.labels))
    def calculate(x):
        geometry=JointMarginal.calculate(p,x);features=geometry['features']
        raw=p.values-p.q*geometry['intercept']-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=skew_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
                         phase_indices,model['nu'],kappa,powers=np.asarray(powers)[present])
        bound=scale_posterior(bound,scale)
        bound['gaussian_precision']/=scale[:,None]*scale[None,:]
        bound['gaussian_covariance']*=scale[:,None]*scale[None,:]
        bound['latent_coefficient']=bound['coefficient'].copy();bound['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@bound['coefficient']
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        geometry.update(bound)
        return geometry
    p.calculate=calculate
    return p


def attach_skew_predictive(p,entries,powers):
    if not entries:return p
    if p.skew_kappa==0:return attach_predictive_linear(p,entries,powers)
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    curved=p.calculate
    def calculate(x):
        c=curved(x);geometry=geometry_features(view,x,0.)
        features=geometry['features'];mean=view.q*geometry['intercept']+features@c['coefficient']
        prediction=predictive_residual(values-mean,features,c['gaussian_precision'],sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo'];c['linear_predictive_objective']=prediction['objective']
        c['negative_twice_elbo']+=prediction['objective'];c['normalization_constant']+=prediction['normalization_constant']
        c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=values-mean;c['linear_elevation']=geometry['elevation']
        return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_slices=slices;p.linear_entries=entries
    return p
