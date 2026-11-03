"""A fixed RF-qualified covariance block for one original curved component.

Other components retain their existing diagonal noise. Original predictive
observations use the exact changed curved precision and their original noise.
"""

import copy

import numpy as np

from ds23_radio_correlation import whitener
from ds23_temporal_noise_problem import attach_temporal_prediction
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior
from compare_dsx01_frame_joint import conditional_gate
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile,whitening


def deterministic_checks(diagnostics):
    return bool(diagnostics['mean_z']<=3 and diagnostics['slope_z']<=3 and
        diagnostics['quadratic_bic_gain']<=10 and diagnostics['maximum_step_z']<=4)


def innovation_noise_screen(standardized,times):
    # batch_noise_screen's 75Hz floor is dimensional. Map standardized noise
    # to75Hz so its floor is exactly one in normalized innovation units.
    return {k:v[0] for k,v in batch_noise_screen((75.*np.asarray(standardized))[None,:],times).items()}


def make_target_problem(d,arm,reference,target_component,alpha,tau,noise_scale=1.):
    p=make_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(reference),d['powers'],d['means'],d['model']['multiplier'],d['model']['nu'])
    p.point_noise=p.point_noise.copy();p.events=[];blocks=[];offset=0;noise_logdet=0.
    for k,(row,sl) in enumerate(zip(p.rows,p.slices,strict=True)):
        target=row['component']==target_component
        if target:p.point_noise[sl]*=noise_scale
        indices=np.arange(sl.start,sl.stop)[p.keep[sl]]
        if not len(indices):continue
        w,ld=whitener(p.flat_times[indices],p.point_noise[indices],alpha if target else 0.,tau)
        to=slice(offset,offset+len(indices));offset+=len(indices);blocks.append((indices,to,w));noise_logdet+=d['powers'][k]*ld
    begin=p.hardware.shape[1]+p.smooth.shape[1];width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=d['means']/p.phase_sigma
    prior_groups=np.full(width,-1,int)
    if d['model']['nu'] is not None:prior_groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    groups=p.noise_groups[p.keep];present=np.unique(groups)
    def calculate(position):
        geometry=geometry_features(p,position,0.);features=geometry['features'];raw=p.values-p.q*geometry['intercept']-features@mean
        y=np.empty(offset);u=np.empty((offset,width))
        for indices,to,w in blocks:y[to]=w@raw[indices];u[to]=w@features[indices]
        scales=np.ones(width);scales[-len(p.members):]=.3
        c=hierarchical_bound(y,u*scales,np.ones(offset),groups,powers=np.asarray(d['powers'])[present],
            prior_groups=prior_groups,prior_nu=d['model']['nu'] or 4.)
        c=scale_posterior(c,scales);c['latent_coefficient']=c['coefficient'].copy();c['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=c['noise_precision'];c['noise_precision']=precision
        c['conditional_residual_hz']=p.values-p.q*geometry['intercept']-features@c['coefficient']
        c['normalization_constant']+=noise_logdet;c['negative_twice_elbo']+=noise_logdet
        if noise_logdet<0:raise ValueError('positive native Hz noise log-volume required')
        c['residual']=np.r_[c['residual'],np.sqrt(noise_logdet)]
        weights=np.asarray(d['powers'])[groups]*precision[groups]
        c['curved_posterior_gram']=np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:,None])
        geometry.update(c);return geometry
    p.calculate=calculate
    attach_temporal_prediction(p,d['entries'],d['powers'],0.,tau)
    p.target_covariance=dict(component=target_component,alpha=alpha,tau_s=tau,noise_scale=noise_scale)
    return p


def retained_covariance_metrics(p,x):
    # Reapply the original composite gates, changing the residual coordinate
    # for the qualified component's stochastic tests, never its raw trend gates.
    scan,state=p.scan,p.state(x);c=p.calculate(x);frequency,elevation=p.conditional_frequency(x);rows=[];model=p.target_covariance
    for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        track=scan.tracks[i];use=p.keep[sl]
        if not use.any():continue
        times=track['times'][use];q=track['rf_hz']/11.5e9
        y=track['values']-scan.hardware(track,state['beta'])-q*scan.rx_basis[i]@state['smooth'][track['receiver']-1]
        terms=profile(y[use],q*frequency[sl][use],*whitening(times));profile_noise={k:v[0] for k,v in batch_noise_screen(terms['innovations'],times).items()}
        residual=c['conditional_residual_hz'][sl][use];conditional=conditional_gate(residual,times);extra={}
        target=row['component']==model['component'] and model['alpha']>0
        if target:
            w,_=whitener(times,p.point_noise[sl][use],model['alpha'],model['tau_s'])
            conditional_white=innovation_noise_screen(w@residual,times)
            profile_white=innovation_noise_screen(w@terms['residual'][0],times)
            profile_pass=deterministic_checks(profile_noise) and profile_white['noise_screen_pass']
            raw_conditional=copy.deepcopy(conditional)
            conditional['compatible']=bool(conditional['rms_hz']<=450 and deterministic_checks(raw_conditional['diagnostics']) and conditional_white['noise_screen_pass'])
            conditional['raw_diagnostics']=raw_conditional['diagnostics'];conditional['diagnostics']=conditional_white
            extra=dict(raw_conditional_gate=raw_conditional,raw_profile_diagnostics=profile_noise,
                profile_innovation_diagnostics=profile_white,covariance_aware_component=True)
        else:profile_pass=profile_noise['noise_screen_pass']
        passing=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and profile_pass and conditional['compatible']
            and int(terms['alias'][0])==alias and elevation[sl][use].min()>=0)
        rows.append(dict(component=track['key'],norad=row['candidate_norad'],candidate_index=row['candidate_index'],points=int(use.sum()),
            compatible=passing,observation_ids=np.asarray(track['observation_ids'])[use].tolist(),conditional_residual_gate=conditional,
            profile_rms_hz=float(terms['rms'][0]),profile_bias_hz=float(terms['bias'][0]),aliases_changed=int(int(terms['alias'][0])!=alias),**extra))
    while True:
        owners={};lookup={t['key']:t for t in scan.tracks};changed=False
        for r in rows:
            if r['compatible']:
                t=lookup[r['component']];owners.setdefault(r['candidate_index'],set()).add((t['receiver'],t['channel']))
        for r in rows:
            if r['compatible'] and r['candidate_index'] in p.supported and len(owners[r['candidate_index']])<2:r['compatible']=False;changed=True
        if not changed:break
    return dict(tracks=rows,accepted_points=sum(r['points'] for r in rows if r['compatible']))
