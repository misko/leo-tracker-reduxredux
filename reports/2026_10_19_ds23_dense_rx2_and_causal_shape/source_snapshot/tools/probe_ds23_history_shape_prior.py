"""Apply qualified pre-RF orbital-shape distributions to matched position fits."""

import argparse
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_causal_shape_distribution import OUT
from ds23_precision_diagnostics import compare_screens
from dsx01_hierarchical_bound import hierarchical_bound
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_receiver_smooth_prior import scale_posterior
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE,context
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha


def shape_coordinates(begin,labels,supported,members,covariance,student):
    start=begin+labels;ecc=start+3*supported;width=ecc+2*supported+members
    transform=np.eye(width);group=np.full(width,-1,int);root=np.linalg.cholesky(covariance)
    for k in range(supported):
        ix=[*range(start+3*k,start+3*k+3),*range(ecc+2*k,ecc+2*k+2)]
        transform[np.ix_(ix,ix)]=root
        if student:group[ix]=labels+k
    return transform,group


def distribution_problem(scan,node,keep,arm,reference,powers,means,model,noise,distribution,mode):
    p=eccentric_problem(scan,node,keep,arm,reference,powers,means,model,noise)
    old=p.calculate;begin=p.hardware.shape[1]+p.smooth.shape[1]
    student=distribution['nu'] is not None and mode=='trained'
    if student and model['nu'] not in (None,distribution['nu']):raise ValueError('this prototype requires matching phase/shape Student degrees')
    transform,groups=shape_coordinates(begin,len(p.labels),len(p.supported),len(p.members),np.array(distribution['covariance']),student)
    if model['nu'] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    width=len(groups);mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    nu=distribution['nu'] if student else (model['nu'] or 4.)
    def calculate(x):
        c=old(x);features=c['features']@transform;scale=np.ones(width);scale[-len(p.members):]=.3
        raw=p.values-p.q*c['intercept']-features@mean;present=np.unique(p.noise_groups[keep])
        b=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=groups,prior_nu=nu)
        b=scale_posterior(b,scale);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=b['noise_precision'];b['noise_precision']=precision
        b['conditional_residual_hz']=p.values-p.q*c['intercept']-features@b['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep])))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)];c.update(b,features=features)
        return c
    p.calculate=calculate;return p


def refit(scan,node,keep,powers,noise,model,arm,distribution,mode):
    base=problem(scan,node,arm,keep);_,receipt=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipt,model['shrinkage']);reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=distribution_problem(scan,node,keep,arm,reference,powers,means,model,noise,distribution,mode)
        r=fit(p,x,iterations=48);x=np.array(r['parameters']);history.append(r)
        reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
    c=p.calculate(x);tracks=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=keep[sl]
        if not active.any():continue
        residual=c['conditional_residual_hz'][sl][active];sigma=p.point_noise[sl][active];time=p.flat_times[sl][active]
        tracks.append(dict(track=scan.tracks[i]['key'],norad=row['candidate_norad'],time_s=time,sigma_hz=sigma,
            conditional_residual_hz=residual,screens=compare_screens(residual,time,sigma)))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,state=p.state(x),
        negative_twice_elbo=c['negative_twice_elbo'],active_points=int(keep.sum()),phase_reference=reference,
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),gates=retained_metrics(p,x),tracks=tracks,
        shape_prior_mode=mode,shape_prior_nu=distribution['nu'] if mode=='trained' else None,
        full_phase_and_shape_parameters_integrated=True)


def run(case,mode='trained',limit=None):
    path=OUT/(case+'.json');distribution=read(path)['selection']
    if not distribution['qualified']:raise ValueError('pre-RF validation did not qualify a shape distribution')
    scan,node,keep,powers,noise,radio,model,old,offsets=context(case,True)
    catalogue=read(CATALOGUE/(case+'_companion.json'))
    candidates=sorted([r for r in catalogue['trials'] if 'arms' in r],key=lambda r:r['arms']['c0']['negative_twice_elbo'])
    if limit is not None:candidates=candidates[:limit]
    trials=[]
    for proposal in candidates:
        candidate=changed_node(scan,node,proposal['proposal']['changes'])
        arms={a:refit(scan,candidate,keep,powers,noise,model,a,distribution,mode) for a in ('c0','fitted_c')}
        legacy=all(t['compatible'] for a in arms.values() for t in a['gates']['tracks'])
        precise=legacy and all(t['screens']['RF_scaled']['noise_screen_pass'] for a in arms.values() for t in a['tracks'])
        trials.append(dict(proposal=proposal['proposal'],arms=arms,legacy_paired_valid=legacy,precision_paired_valid=precise))
        write(OUT/(case+'_'+mode+'_position_partial.json'),dict(case=case,trials=trials))
        print(case,mode,'NORAD',proposal['proposal']['norad'],'legacy',legacy,'precision',precise,flush=True)
    legacy=[r for r in trials if r['legacy_paired_valid']];precise=[r for r in trials if r['precision_paired_valid']]
    key=lambda r:r['arms']['c0']['negative_twice_elbo']
    write(OUT/(case+'_'+mode+'_position.json'),dict(case=case,trials=trials,
        legacy_chosen=min(legacy,key=key) if legacy else None,precision_chosen=min(precise,key=key) if precise else None,
        baseline=catalogue['chosen'],mode=mode,distribution=distribution,distribution_sha256=sha(path),
        catalogue_sha256=sha(CATALOGUE/(case+'_companion.json')),source_sha256=sha(Path(__file__)),
        GPS_used=False,paired_c=True,observations_masks_aliases_noise_and_other_priors_match=True,
        identity_proposals_frozen_from_previous_full_causal_catalogue_screen=True,
        precision_screen_is_development_safety_check_not_independently_calibrated=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--mode',choices=['trained','Gaussian'],default='trained');parser.add_argument('--limit',type=int)
    args=parser.parse_args();run(args.case,args.mode,args.limit)
