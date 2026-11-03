"""Modular predictive likelihood for native peaks sharing a receiver probe.

Condition new measurement errors on the existing simultaneous curved point.
All original predictive tracks and added conditional observations are integrated
in one block, preserving their shared curved-calibration covariance. Calibration
means remain curved-only at each position, as in the existing linear policy.
"""

import numpy as np
from ds23_predictive_linear import linear_geometry,predictive_residual
from ds23_height_problem import geometry_features


def symmetrized_RF_covariance(first_sigma,second_sigma,covariance,floor=5.):
    values=np.array([first_sigma,second_sigma,covariance,floor],float)
    if not np.isfinite(values).all() or min(first_sigma,second_sigma,floor)<=0:
        raise ValueError('finite positive RF scales required')
    variance=(first_sigma**2+second_sigma**2)/2
    if variance<=floor**2:raise ValueError('total RF variance must exceed independent floor')
    common=float(np.clip(covariance,0,variance-floor**2))
    kappa=common/variance
    return dict(variance_hz2=float(variance),common_variance_hz2=common,kappa=kappa,
        conditional_sigma_hz=float(np.sqrt(variance*(1-kappa*kappa))),
        marginal_sigma_hz=float(np.sqrt(variance)),
        physical_equal_common_frequency_loading_assumed=True)


def condition_rows(values,features,mean,primary_values,primary_features,primary_mean,rows,anchors,kappa):
    y,u,m=np.asarray(values).copy(),np.asarray(features).copy(),np.asarray(mean).copy()
    rows,anchors=np.asarray(rows,int),np.asarray(anchors,int)
    if rows.shape!=anchors.shape or len(set(rows))!=len(rows):raise ValueError('unique aligned conditional rows required')
    y[rows]-=kappa*np.asarray(primary_values)[anchors]
    u[rows]-=kappa*np.asarray(primary_features)[anchors]
    m[rows]-=kappa*np.asarray(primary_mean)[anchors]
    return y,u,m


def attach_probe_prediction(p,entries,powers,conditioned_entries,RF_covariance,correlated):
    """entries include unchanged originals followed by research secondary tracks.

    conditioned_entries maps each new component to flat curved anchor indices.
    Likelihood powers/Gamma noise in the original bound remain unchanged. The
    added block is a conditional generalized predictive approximation, not a
    claim that the complete variational score is a calibrated joint density.
    """
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries)
    row_indices=[];anchor_indices=[]
    for entry,sl in zip(entries,slices,strict=True):
        if entry['component'] not in conditioned_entries:continue
        anchors=conditioned_entries[entry['component']]
        if len(anchors)!=sl.stop-sl.start:raise ValueError('one curved anchor per new simultaneous observation required')
        row_indices.extend(range(sl.start,sl.stop));anchor_indices.extend(anchors)
    rows=np.asarray(row_indices,int);anchors=np.asarray(anchor_indices,int)
    if np.any(~p.keep[anchors]):raise ValueError('conditioning requires original active curved data')
    kappa=RF_covariance['kappa'] if correlated else 0.
    # The existing predictive policy uses E[1/tau]=2 for unseen Gamma(2,2)
    # noise. Retain it for the added measurements and both comparison arms.
    sigma=sigma.copy();sigma[rows]=RF_covariance['marginal_sigma_hz']*np.sqrt(1-kappa*kappa)
    curved=p.calculate
    def calculate(position):
        c=curved(position);g=p.noise_groups[p.keep]
        w=np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u=c['features'][p.keep]
        gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        geometry=geometry_features(view,position,0.)
        secondary_mean=view.q*geometry['intercept']+geometry['features']@c['coefficient']
        primary_mean=p.q*c['intercept']+c['features']@c['coefficient']
        y,design,mean=condition_rows(values,geometry['features'],secondary_mean,p.values,c['features'],primary_mean,rows,anchors,kappa)
        prediction=predictive_residual(y-mean,design,gram,sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo']
        c['linear_predictive_objective']=prediction['objective'];c['negative_twice_elbo']+=prediction['objective']
        c['normalization_constant']+=prediction['normalization_constant'];c['residual']=np.r_[c['residual'],prediction['residual']]
        c['linear_raw_prediction_residual_hz']=y-mean;c['linear_elevation']=geometry['elevation']
        c['shared_probe_kappa']=kappa;c['conditional_measurements']=len(rows)
        c['linear_calibration_coefficient_unchanged']=True
        return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_slices=slices;p.linear_entries=entries
    return p
