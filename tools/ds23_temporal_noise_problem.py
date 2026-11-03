"""Correlated GLRT likelihood with curved-only calibration and prediction."""

import numpy as np
from ds23_frozen_precision import conditional_gaussian
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from ds23_radio_correlation import whitener
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior


def correlated_prediction(raw,design,gram,sigma,times,slices,alpha,tau):
    y=np.asarray(raw,float);u=np.asarray(design,float)
    root=np.linalg.cholesky(gram);uncertainty=np.linalg.solve(root,u.T).T
    bias=np.zeros((len(y),len(slices)))
    for k,sl in enumerate(slices):bias[sl,k]=300.
    features=np.column_stack((uncertainty,bias));white_y=np.empty_like(y);white_u=np.empty_like(features);logdet=0.
    for sl in slices:
        w,ld=whitener(times[sl],sigma[sl],alpha,tau)
        white_y[sl]=w@y[sl];white_u[sl]=w@features[sl];logdet+=ld
    result=conditional_gaussian(white_y,white_u,np.full(len(y),np.sqrt(2.)),np.ones(len(y)),
        np.ones(len(y)),np.ones(features.shape[1]),1.)
    result["objective"]+=logdet;result["negative_twice_elbo"]+=logdet
    result["normalization_constant"]+=logdet
    # The likelihood determinant is fixed across positions. Include it in the
    # least-squares representation as well, without counting it twice in ELBO.
    if logdet<0:raise ValueError("positive Hz-scale noise log determinant expected")
    result["residual"]=np.r_[result["residual"],np.sqrt(logdet)]
    return result


def make_temporal_problem(scan,node,keep,arm,reference,powers,means,model,alpha,tau,noise_scale=1.):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model["multiplier"],model["nu"])
    if not np.isfinite(noise_scale) or noise_scale<=0:raise ValueError("positive finite radio noise scale required")
    p.point_noise=p.point_noise*noise_scale
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    prior_groups=np.full(width,-1,int)
    if model["nu"] is not None:prior_groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    blocks=[];noise_logdet=0.;offset=0
    for k,sl in enumerate(p.slices):
        indices=np.arange(sl.start,sl.stop)[keep[sl]]
        if not len(indices):continue
        w,ld=whitener(p.flat_times[indices],p.point_noise[indices],alpha,tau)
        target=slice(offset,offset+len(indices));offset+=len(indices)
        blocks.append((indices,target,w));noise_logdet+=powers[k]*ld
    if noise_logdet<0:raise ValueError("positive Hz-scale noise log determinant expected")
    groups=p.noise_groups[keep];present=np.unique(groups)
    def calculate(position):
        geometry=geometry_features(p,position,0.);features=geometry["features"]
        raw=p.values-p.q*geometry["intercept"]-features@mean
        white_y=np.empty(offset);white_u=np.empty((offset,width))
        for indices,target,w in blocks:
            white_y[target]=w@raw[indices];white_u[target]=w@features[indices]
        scale=np.ones(width);scale[-len(p.members):]=.3
        result=hierarchical_bound(white_y,white_u*scale,np.ones(offset),groups,powers=powers[present],
            prior_groups=prior_groups,prior_nu=model["nu"] or 4.)
        result=scale_posterior(result,scale)
        result["latent_coefficient"]=result["coefficient"].copy();result["coefficient"]+=mean
        precision=np.zeros(len(p.members));precision[present]=result["noise_precision"];result["noise_precision"]=precision
        result["conditional_residual_hz"]=p.values-p.q*geometry["intercept"]-features@result["coefficient"]
        result["normalization_constant"]+=noise_logdet;result["negative_twice_elbo"]+=noise_logdet
        result["residual"]=np.r_[result["residual"],np.sqrt(noise_logdet)]
        weight=powers[groups]*precision[groups]
        result["curved_posterior_gram"]=np.diag(result["coefficient_prior_precision"])+white_u.T@(white_u*weight[:,None])
        geometry.update(result);return geometry
    p.calculate=calculate
    return p


def attach_temporal_prediction(p,entries,powers,alpha,tau,noise_scale=1.):
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    sigma=sigma*noise_scale
    curved_calculate=p.calculate
    def calculate(position):
        c=curved_calculate(position);g=geometry_features(view,position,0.)
        mean=view.q*g["intercept"]+g["features"]@c["coefficient"]
        prediction=correlated_prediction(values-mean,g["features"],c["curved_posterior_gram"],
            sigma,view.flat_times,slices,alpha,tau)
        c["curved_negative_twice_elbo"]=c["negative_twice_elbo"]
        c["linear_predictive_objective"]=prediction["objective"]
        c["negative_twice_elbo"]+=prediction["objective"]
        c["normalization_constant"]+=prediction["normalization_constant"]
        c["residual"]=np.r_[c["residual"],prediction["residual"]]
        c["linear_raw_prediction_residual_hz"]=values-mean;c["linear_elevation"]=g["elevation"]
        return c
    p.calculate=calculate;p.curved_calculate=curved_calculate;p.linear_slices=slices;p.linear_entries=entries
    return p
