"""Local timing-measurement design and independent-factor position sensitivity.

Design uses curved RF evidence and its conditional Gamma precisions only.
Linear tracks remain predictive. No evaluation coordinate or phase truth is
read to select which satellite to measure. This is an information diagnostic,
not a source of actual independent ephemeris measurements.
"""

import numpy as np
from ds23_gaussian_information import gaussian_factor_bound,greedy_phase_design
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_predictive_linear import linear_geometry,predictive_residual
from ds23_height_problem import geometry_features
from dsx01_joint_marginal import JointMarginal


def local_design(p,position,*,step_km=.025):
    x=np.asarray(position,float);c=p.calculate(x);keep=np.asarray(p.keep,bool)
    derivatives=[]
    for axis in np.eye(2)*step_km:
        values=[]
        for point in (x-axis,x+axis):
            g=JointMarginal.calculate(p,point)
            values.append(p.q*g['intercept']+g['features']@c['coefficient'])
        derivatives.append((values[1]-values[0])/(2*step_km))
    d=np.column_stack(derivatives)[keep];u=c['features'][keep]
    weights=np.asarray(p.design_powers)[p.noise_groups[keep]]*c['noise_precision'][p.noise_groups[keep]]/p.point_noise[keep]**2
    a=np.column_stack((d,u));precision=a.T@(a*weights[:,None])
    precision[2:,2:]+=np.diag(c['coefficient_prior_precision'])
    root=np.linalg.cholesky(precision);inverse=np.linalg.solve(root,np.eye(len(root)))
    covariance=inverse.T@inverse
    begin=2+p.hardware.shape[1]+p.smooth.shape[1]
    scale=np.ones(len(covariance));scale[begin:begin+len(p.labels)]=p.phase_sigma
    covariance=covariance*scale[:,None]*scale[None,:]
    counts=np.zeros(len(p.labels),int)
    for row,sl in zip(p.rows,p.slices,strict=True):
        counts[p.labels.index(row['candidate_index'])]+=int(keep[sl].sum())
    eligible=np.flatnonzero(counts>=12)
    return dict(covariance=covariance,phase_coordinates=begin+eligible,
        phase_label_indices=eligible,phase_coordinate_begin=begin,curved_point_counts=counts,
        position_covariance_km2=covariance[:2,:2],position_rms_SD_km=float(np.sqrt(np.trace(covariance[:2,:2]))),
        conditional_on_Gamma_precisions_and_frozen_nominations=True,
        predictive_linear_excluded_from_calibration=True,finite_difference_step_km=step_km)


def choose_labels(design,sigma_s,budget,method='information',seed=0):
    eligible=np.asarray(design['phase_label_indices'],int)
    if method=='information':
        selected=greedy_phase_design(design['covariance'],np.asarray(design['phase_coordinates']),sigma_s,budget)
        labels=[int(k-design['phase_coordinate_begin']) for k in selected['coordinates']]
        return dict(label_indices=labels,history=selected['history'],
            predicted_position_rms_SD_km=float(np.sqrt(np.trace(selected['covariance'][:2,:2]))))
    if method=='point_count':
        counts=np.asarray(design['curved_point_counts']);ordered=sorted(eligible,key=lambda k:(-counts[k],k))
    elif method=='random':ordered=np.random.default_rng(seed).permutation(eligible).tolist()
    else:raise ValueError('information, point_count or random design required')
    return dict(label_indices=[int(k) for k in ordered[:budget]])


def make_phase_measured_problem(scan,node,keep,arm,reference,powers,means,model,measurements):
    p=make_event_problem(scan,node,keep,arm,reference,powers,means,model,[])
    if not measurements:return p
    nb,ns=p.hardware.shape[1],p.smooth.shape[1];begin=nb+ns
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    scales=np.ones(width);scales[-len(p.members):]=.3
    prior=np.full(width,-1,int)
    if model['nu'] is not None:prior[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    factor=np.zeros((len(measurements),width))
    for k,r in enumerate(measurements):
        if r['candidate_index'] not in p.labels:raise ValueError('measured satellite absent from original phase coordinates')
        index=p.labels.index(r['candidate_index']);factor[k,begin+index]=p.phase_sigma[index]
    values=np.array([r['phase_s'] for r in measurements]);sigma=np.array([r['sigma_s'] for r in measurements])
    present=np.unique(p.noise_groups[keep])
    def calculate(position):
        geometry=JointMarginal.calculate(p,position);features=geometry['features']
        raw=p.values-p.q*geometry['intercept']-features@mean
        bound=gaussian_factor_bound(raw[keep],(features*scales)[keep],p.point_noise[keep],p.noise_groups[keep],
            values-factor@mean,factor*scales,sigma,powers=np.asarray(powers)[present],
            prior_groups=None if model['nu'] is None else prior,prior_nu=4 if model['nu'] is None else model['nu'])
        latent=bound['coefficient']*scales;bound['coefficient']=latent+mean;bound['latent_coefficient']=latent
        bound['coefficient_prior_precision']/=scales**2
        bound['calibration_posterior_precision']=bound['coefficient_posterior_precision']/scales[:,None]/scales[None,:]
        noise=np.zeros(len(p.members));noise[present]=bound['noise_precision'];bound['noise_precision']=noise
        bound['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@bound['coefficient']
        bound['phase_measurement_residual_s']=values-factor@bound['coefficient']
        bound['phase_measurement_sigma_s']=sigma
        volume=float(2*np.sum(np.asarray(powers)[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        geometry.update(bound);return geometry
    p.calculate=calculate;p.independent_phase_measurements=measurements
    return p


def attach_phase_measured_predictive(p,entries,powers):
    if not getattr(p,'independent_phase_measurements',[]):return attach_event_predictive(p,entries,powers)
    if not entries:return p
    view,values,sigma,groups,slices=linear_geometry(p,entries);curved=p.calculate
    def calculate(position):
        c=curved(position);g=geometry_features(view,position,0.)
        predicted=view.q*g['intercept']+g['features']@c['coefficient']
        bound=predictive_residual(values-predicted,g['features'],c['calibration_posterior_precision'],sigma*np.sqrt(2),groups)
        c['curved_negative_twice_elbo']=c['negative_twice_elbo'];c['negative_twice_elbo']+=bound['objective']
        c['normalization_constant']+=bound['normalization_constant'];c['residual']=np.r_[c['residual'],bound['residual']]
        c['linear_raw_prediction_residual_hz']=values-predicted;c['linear_elevation']=g['elevation'];return c
    p.calculate=calculate;p.curved_calculate=curved;p.linear_entries=entries;p.linear_slices=slices
    return p
