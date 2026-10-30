"""Causal identity evidence for tracks excluded from curved calibration.

New tracks never enter receiver or orbit calibration normal equations. Existing
family posteriors are shared; absent families get independent causal priors.
"""
import argparse
from pathlib import Path
import time
import numpy as np
from scipy.linalg import cho_solve
from scipy.stats import norm,t as student
from annotate_track_predictively import fit_training,nominate,corrected,SEEDS
from diagnose_all_large_tracks import context,ARMS
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import grouped_split,identity_consensus
from leo.analysis.research.predictive_track import receiver_design,mixture_prediction
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon


def calibration_covariance(p,x):
    c=p.calculate(x);u=c['features'][p.keep];g=p.noise_groups[p.keep]
    w=c['noise_precision'][g]/p.point_noise[p.keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
    return c,cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)))


def prediction_design(p,track,label,base,width):
    """Include receiver events in predictive means and their full covariance."""
    from ds23_frequency_events import track_events
    base=np.asarray(base,float);events=getattr(p,'events',[])
    boundary=p.event_start if events else width
    if base.ndim!=2 or base.shape[0]!=len(track['times']) or base.shape[1]>boundary:
        raise ValueError('predictive base overlaps event coordinates')
    result=np.zeros((len(track['times']),width));result[:,:base.shape[1]]=base
    if events:
        if boundary+len(events)!=width:raise ValueError('event posterior width mismatch')
        result[:,boundary:]=track_events(track,label,events)
    return result


def prediction_models(d,p,x,i,j,*,phase_step=.1,uncalibrated_phase_mixture=False,return_frozen_covariance=False):
    """Mean/covariance mixture with original calibration coefficients untouched."""
    from ds23_predictive_linear import linear_geometry
    from ds23_height_problem import geometry_features
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    from build_dsx01_orbit_modes import build_modes
    c,covcoef=calibration_covariance(p,x);before=c['coefficient'].copy();track=d['scan'].tracks[i]
    times=track['times'];n=len(times);q=track['rf_hz']/11.5e9
    # Predeclared noise; no target-dependent window/noise selection. Gamma(2,2)
    # predictive noise contributes E[1/tau]=2; one independent 300 Hz bias.
    fixed=np.eye(n)*150.**2*2+300.**2
    active=any(r['candidate_index']==j and p.keep[sl].any() for r,sl in zip(p.rows,p.slices,strict=True))
    if j in p.labels and not (uncalibrated_phase_mixture and not active):
        if return_frozen_covariance:raise ValueError('frozen receiver decomposition requires an uncalibrated satellite family')
        view,*_=linear_geometry(p,[dict(track_index=i,candidate_index=j,alias=0)])
        geometry=geometry_features(view,x,0.);h=prediction_design(p,track,j,geometry['features'],len(before))
        means=(q*geometry['intercept']+h@c['coefficient'])[None]
        covariance=(fixed+h@covcoef@h.T)[None]
        phases=np.array([p.state(x)['phases'][j]]);logprior=np.zeros(1)
        elevations=np.array([geometry['elevation'].min()]);receipt=dict(kind='existing_shared_posterior',candidate_index=j,active_curved_family=active)
    else:
        receiver=receiver_design(times,track['rf_hz'],track['receiver'],track['channel'],d['scan'].rx_basis[i],fitted_c=p.fitted_c)
        h=prediction_design(p,track,j,receiver,len(before))
        calibration_mean=h@before;frozen_covariance=h@covcoef@h.T;fixed+=frozen_covariance
        widths,history=phase_widths(d['scan'],[j]);mean=float(forecast_phase_mean(history,d['model']['shrinkage'])[0])
        sigma=float(widths[0]*d['model']['multiplier']);nu=d['model']['nu']
        phases=np.linspace(-15,15,int(round(30/phase_step))+1)
        distribution=norm(loc=mean,scale=sigma) if nu is None else student(nu,loc=mean,scale=sigma)
        logprior=distribution.logpdf(phases);logprior[[0,-1]]-=np.log(2)
        bank={key:d['scan'].sky[key][[j]] for key in ['position_km','velocity_km_s']};bank['time_s']=d['scan'].sky['time_s']
        modes,metadata=build_modes(d['scan'],[j],[j],'physical');means=[];covariance=[];elevations=[]
        for phase in phases:
            f,e=paired_phase_frequency(bank,times,np.zeros(n,int),np.array([phase]),*latlon(x))
            u=q*paired_frequency_modes(bank,modes,times,np.zeros(n,int),np.array([phase]),*latlon(x))
            means.append(calibration_mean+q*f);covariance.append(fixed+u@u.T);elevations.append(e.min())
        means=np.asarray(means);covariance=np.asarray(covariance);elevations=np.asarray(elevations)
        receipt=dict(kind='new_family_causal_phase_mixture' if j not in p.labels else 'uncalibrated_family_causal_phase_mixture',
            candidate_index=j,active_curved_family=active,phase_prior_mean_s=mean,phase_prior_sigma_s=sigma,
            phase_prior_nu=nu,prior_mass_in_phase_box=float(distribution.cdf(15)-distribution.cdf(-15)),
            phase_step_s=float(phases[1]-phases[0]),history=history,orbital_prior=metadata)
    logprior[elevations<0]=-np.inf
    np.testing.assert_array_equal(before,p.calculate(x)['coefficient'])
    result=(means,covariance,logprior,phases,elevations,receipt)
    return result+(frozen_covariance,) if return_frozen_covariance else result


def check_predictive_role(p,track_index,allow_inactive_member=False):
    if track_index not in p.members:return
    if not allow_inactive_member:raise ValueError('use curved annotation for a calibration member')
    k=p.members.index(track_index)
    if p.keep[p.slices[k]].any():raise ValueError('predictive-role target already has active calibration observations')


def run(args):
    if sum(bool(getattr(args,k,None)) for k in ('inactive_fragment','native_branches','graph_bundle'))>1:
        raise ValueError('choose one predictive source type')
    if getattr(args,'inactive_fragment',False) and getattr(args,'native_branches',None):
        raise ValueError('choose an inactive graph fragment or an omitted native branch')
    began=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    inv=read(args.inventory);d=context(inv);p0,_=d['problems']['c0']
    if getattr(args,'graph_bundle',None):
        from predictive_graph_bundle import bundle_context
        d,target=bundle_context(d,inv,args.graph_bundle,args.track)
    elif getattr(args,'native_branches',None):
        from native_predictive_branch import native_context
        d,target=native_context(d,inv,args.native_branches,args.track)
    elif getattr(args,'inactive_fragment',False):
        from inactive_graph_fragment import inactive_fragment_context
        d,target=inactive_fragment_context(d,inv,args.track)
    else:target=next(r for r in inv['tracks'] if r['track_id']==args.track and r['current_large'])
    i=target['track_index'];t=d['scan'].tracks[i]
    check_predictive_role(p0,i,getattr(args,'predictive_member',False))
    full_times=np.r_[p0.flat_times,t['times']];n=len(p0.flat_times)
    from annotation_partition_plan import selected_seeds
    seeds,partition_plan=selected_seeds(getattr(args,'partition_audit',None),target['track_id'],full_times,t['times'],SEEDS,
        distinct=getattr(args,'distinct_partitions',False))
    write(out/'protocol.json',dict(job=inv['job'],target=target,seed_list=seeds[:args.folds],partition_plan=partition_plan,block_s=12,guard_s=2,
        target_used_for_calibration=False,conditional_on_frozen_graph_and_incumbent_identities=True,
        inactive_curved_member_as_predictive=bool(i in p0.members),
        fixed_noise_hz=150,unseen_noise_variance_multiplier=2,track_bias_sigma_hz=300,
        phase_box_s=[-15,15],phase_step_s=args.phase_step,uncalibrated_phase_mixture=args.uncalibrated_phase_mixture,phase_rounds=5,position_steps=48,
        identity_score_name='conditional_target',position_uncertainty_integrated=False,
        learned_noise_precision_uncertainty_integrated=False,GPS_used=False,future_TLE=False))
    results=[]
    for seed in seeds[:args.folds]:
        if len(np.unique(np.floor(t['times']/12)))<3:
            write(out/f'seed-{seed}.json',dict(status='insufficient_group_support',seed=seed));continue
        train,held,split=grouped_split(full_times,t['times'],seed=seed);train_target,held_target=train[n:],held[n:]
        if train_target.sum()<8 or held_target.sum()<4:
            write(out/f'seed-{seed}.json',dict(status='insufficient_group_support',seed=seed,split=split));continue
        keep=d['keep']&train[:n];base={a:fit_training(d,d['node'],keep,a) for a in ARMS}
        offers,receipt=nominate(d,base,i,train_target,args.candidates)
        write(out/f'nominations-{seed}.json',dict(selected=offers,nomination=receipt,split=split))
        proposals=[]
        for offer in offers:
            j=offer['candidate_index'];norad=int(d['scan'].norads[j]);bank={key:d['scan'].sky[key][[j]] for key in ['position_km','velocity_km_s']};bank['time_s']=d['scan'].sky['time_s']
            tt=t['times'][train_target]
            f,_=paired_phase_frequency(bank,tt,np.zeros(len(tt),int),np.array([offer['phase_s']]),*latlon(offer['position']))
            p,x,_=base['c0'];alias=int(profile_rate(corrected(p,x,i)[train_target],t['rf_hz']/11.5e9*f,tt)['alias'][0])
            observed=t['values']+alias*PERIOD;arms={}
            for arm,(p,x,meta) in base.items():
                means,cov,lp,phases,elevations,prior=prediction_models(d,p,x,i,j,phase_step=args.phase_step,
                    uncalibrated_phase_mixture=args.uncalibrated_phase_mixture)
                if np.isfinite(lp).any():
                    score=mixture_prediction(observed,means,cov,lp,train_target,held_target)
                    weights=score['training_mixture_weights'];visible=float(elevations[weights>1e-6].min())
                    phase_mean=float(weights@phases);phase_sd=float(np.sqrt(weights@((phases-phase_mean)**2)))
                    boundary=float(weights[abs(phases)>=14.9].sum()) if len(phases)>1 else float(abs(phases[0])>=14.9)
                else:
                    score=dict(negative_twice_log_density=1e30,rms_hz=1e15,unobservable=True);visible=float(elevations.max());phase_mean=phase_sd=boundary=None
                arms[arm]=dict(**meta,scores={'conditional_target':score,'target':score},prior=prior,
                    minimum_target_elevation_deg=visible,target_phase_training_mean_s=phase_mean,
                    target_phase_training_sigma_s=phase_sd,target_phase_boundary_mass=boundary,
                    target_enters_calibration_equations=False)
                if target.get('graph_bundle'):
                    members=np.asarray(target['member_indices']);checks={}
                    for k,member in enumerate(target['members']):
                        held_member=held_target&(members==k)
                        if held_member.sum()<4:continue
                        z=mixture_prediction(observed,means,cov,lp,train_target,held_member) if np.isfinite(lp).any() else dict(negative_twice_log_density=1e30,rms_hz=1e15)
                        checks[member['track_id']]=dict(z,held_points=int(held_member.sum()))
                    arms[arm]['bundle_member_scores']=checks
            q=dict(candidate_index=j,norad=norad,alias=alias,arms=arms);proposals.append(q);write(out/f'{seed}-{norad}.json',q)
            print(inv['job']['label'],seed,norad,[(a,round(v['scores']['target']['rms_hz'],1)) for a,v in arms.items()],flush=True)
        fold=dict(seed=seed,split=split,proposals=proposals);results.append(fold);write(out/f'seed-{seed}.json',fold)
    annotation=identity_consensus(results,score_name='conditional_target')
    bundle_checks=None
    if target.get('graph_bundle'):
        from predictive_graph_bundle import member_evidence
        bundle_checks=member_evidence(results,target,annotation['norad'])
        if annotation['status']=='conditionally_supported_identity' and not bundle_checks['passed']:
            annotation=dict(annotation,status='bundle_member_support_failed')
    write(out/'result.json',dict(job=inv['job'],component=t['key'],track_id=target['track_id'],folds=results,annotation=annotation,
        graph_bundle=target.get('graph_bundle',False),bundle_member_checks=bundle_checks,
        inactive_graph_fragment=target.get('inactive_graph_fragment',False),
        identity_score_name='conditional_target',inclusion_mode='predictive_only',seconds=time.monotonic()-began,
        annotation_prototype=True,no_accepted_associations=True,
        geometry_only_early_exit=bool(partition_plan and partition_plan.get('geometry_only_early_exit'))))
    print(inv['job']['label'],annotation['status'],annotation['norad'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['inventory','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--track',required=True);p.add_argument('--candidates',type=int,default=3);p.add_argument('--folds',type=int,default=3)
    p.add_argument('--phase-step',type=float,default=.1);p.add_argument('--uncalibrated-phase-mixture',action='store_true')
    p.add_argument('--predictive-member',action='store_true',help='Allow a wholly inactive curved member as predictive-only evidence')
    p.add_argument('--inactive-fragment',action='store_true',help='Assess only parent graph observations unused by both c arms; no position inclusion authorization')
    p.add_argument('--partition-audit',type=Path)
    p.add_argument('--native-branches',type=Path,help='Validated omitted-branch discovery JSON; append only to predictive geometry')
    p.add_argument('--graph-bundle',type=Path,help='Frozen same-lane graph union; conditional hypothesis, not a new calibration curve')
    p.add_argument('--distinct-partitions',action='store_true',help='Select three distinct target holdouts by timestamps; skip RF fits if unavailable')
    run(p.parse_args())
