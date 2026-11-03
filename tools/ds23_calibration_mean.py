"""Known Gaussian receiver-mean translations for calibration invariance controls."""

import numpy as np
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def mean_problem(scan,node,keep,arm,reference,powers,means,model,smooth_index,kappa):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    if not 0<=smooth_index<p.smooth.shape[1] or not np.isfinite(kappa):raise ValueError('valid smooth coordinate and finite Gaussian mean required')
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    mean[p.hardware.shape[1]+smooth_index]=kappa
    prior=np.full(width,-1,int)
    if model['nu'] is not None:prior[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    scale=np.ones(width);scale[-len(p.members):]=.3
    def calculate(position):
        c=geometry_features(p,position,0.);u=c['features'];raw=p.values-p.q*c['intercept']-u@mean
        present=np.unique(p.noise_groups[keep])
        b=hierarchical_bound(raw[keep],(u*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=prior,prior_nu=4 if model['nu'] is None else model['nu'])
        b=scale_posterior(b,scale);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        noise=np.zeros(len(p.members));noise[present]=b['noise_precision'];b['noise_precision']=noise
        b['conditional_residual_hz']=p.values-p.q*c['intercept']-u@b['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)];c.update(b)
        return c
    p.calculate=calculate
    return p
