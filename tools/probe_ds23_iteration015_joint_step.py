"""Test a common event when individually valid curved additions conflict jointly."""

from pathlib import Path
import signal
import numpy as np

import run_ds23_dbg01_iteration_015 as runner
from diagnose_ds23_iteration013_step_transfer import only_step_fails,affine_eliminated_step
from ds23_supported_curvature import curvature_evidence
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import refit
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'joint_curve_shared_step'


def valid_standalone_unions(trials):
    qualified={t['additions'][0]['component'] for t in trials if len(t['additions'])==1 and t['paired_valid']}
    return sorted([t for t in trials if not t['paired_valid'] and len(t['additions'])>=2 and
        {a['component'] for a in t['additions']}<=qualified],key=lambda t:(-t['added_curved_points'],tuple(a['component'] for a in t['additions'])))


def build(d,t,arm,events):
    p=make_event_problem(d['scan'],t['node'],np.asarray(t['mask'],bool),arm,np.asarray(t['arms'][arm]['phase_reference']),
        d['powers'],np.asarray(t['means']),d['model'],events)
    return attach_event_predictive(p,t['entries'],d['powers'])


def coverage(d,t,arm,p):
    old=runner.engine.baseline.build;runner.engine.baseline.build=lambda *_:p
    try:return runner.engine.baseline.inventory(dict(d,arms=t['arms']),arm)
    finally:runner.engine.baseline.build=old


def one(case):
    runner.configure();d=runner.engine.current_setup(case);prior=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))['trials'];targets=[]
    saved=d['arms']['c0'];base=runner.engine.baseline.build(d,'c0',saved['phase_reference']);original=base.calculate(np.asarray(saved['endpoint_east_north_km']))['conditional_residual_hz']
    for joint in valid_standalone_unions(prior)[:1]:
        added_families={a['norad'] for a in joint['additions']}
        for addition in sorted(joint['additions'],key=lambda a:a['component']):
            component=addition['component'];gates=[next(g for g in r['gates']['tracks'] if g['component']==component) for r in joint['arms'].values()]
            if not all(only_step_fails(g) for g in gates):continue
            track=next(t for t in d['scan'].tracks if t['key']==component)
            if not curvature_evidence(track)['qualified']:continue
            p=build(d,joint,'c0',[]);sl=next(s for r,s in zip(p.rows,p.slices,strict=True) if r['component']==component)
            res=p.calculate(np.asarray(joint['arms']['c0']['endpoint_east_north_km']))['conditional_residual_hz'][sl];n=len(res);splits=np.arange(4,n-3)
            a=np.cumsum(res)[splits-1];jump=a/splits-(res.sum()-a)/(n-splits);z=abs(jump)/(max(np.std(res,ddof=1),75)*np.sqrt(1/splits+1/(n-splits)))
            k=int(np.argmax(z));split=int(splits[k]);tau=float(np.mean(track['times'][split-1:split+1]));controls=[]
            for q,(row,index,s) in enumerate(zip(base.rows,base.members,base.slices,strict=True)):
                other=d['scan'].tracks[index];use=base.keep[s];tt=np.asarray(other['times'])[use]
                if other['receiver']!=track['receiver'] or row['candidate_norad'] in added_families or sum(tt<tau)<4 or sum(tt>=tau)<4:continue
                witness=curvature_evidence(dict(other,times=tt,values=np.asarray(other['values'])[use]))
                if not witness['qualified']:continue
                rr=original[s][use];sigma=base.point_noise[s][use]/np.sqrt(d['powers'][q]);control=affine_eliminated_step(tt,rr,sigma,tau)
                controls.append(dict(component=other['key'],norad=row['candidate_norad'],channel=other['channel'],times=tt,residual_hz=rr,curvature=witness,**control))
            targets.append(dict(component=component,norad=addition['norad'],receiver=track['receiver'],channel=track['channel'],time_s=tau,
                times=track['times'],residual_hz=res,mean_difference_hz=float(jump[k]),independent_original_parent_curves=controls,
                null=joint,search_penalty=float(2*np.log(max(1,len(prior))*max(1,n-7)*2))))
    targets=sorted(targets,key=lambda t:(-len(t['times']),t['component']))[:1]
    write(OUT/(case+'_RF_diagnostic.json'),dict(case=case,targets=targets,RF_proposals_frozen_before_new_position_fit=True))
    trials=[];nulls=[]
    for target in targets:
        supports={kind:[r for r in target['independent_original_parent_curves'] if r['gain']>0 and
            r['amplitude_hz']*target['mean_difference_hz']<0 and (kind=='receiver' or (r['channel']>4)==(target['channel']>4))] for kind in ['band','receiver']}
        if not any(supports.values()):continue
        null=target['null'];null_arms={a:refit(d['scan'],null['node'],np.asarray(null['mask'],bool),a,d['powers'],np.asarray(null['means']),d['model'],[],null['entries']) for a in ['c0','fitted_c']}
        nulls.append(dict(null,arms=null_arms,events=[]))
        for kind,witnesses in supports.items():
            if not witnesses:continue
            event=dict(kind=kind,receiver=target['receiver'],time_s=target['time_s'],sigma_hz=300.)
            if kind=='band':event['band']=int(target['channel']>4)
            arms={a:refit(d['scan'],null['node'],np.asarray(null['mask'],bool),a,d['powers'],np.asarray(null['means']),d['model'],[event],null['entries']) for a in ['c0','fitted_c']}
            gains={a:null_arms[a]['negative_twice_elbo']-s['negative_twice_elbo'] for a,s in arms.items()}
            trial=dict(null,arms=arms,events=[event],kind=kind,null_arms=null_arms,gains=gains,search_penalty=target['search_penalty'],paired_valid=bool(valid(arms)))
            trial['coverage']={a:coverage(d,trial,a,build(d,trial,a,[event])) for a in arms};old=read(runner.RAW/case/'inventory.json')['arms']
            trial['accepted']=bool(trial['paired_valid'] and all(s['final_phase_change_s']<=.01 for s in arms.values()) and min(gains.values())>target['search_penalty'] and
                all(set(old[a]['accepted_observation_ids'])<=set(c['accepted_observation_ids']) for a,c in trial['coverage'].items()))
            trials.append(trial);write(OUT/(case+'_checkpoint.json'),dict(trials=trials));print(case,kind,'joint event accepted',trial['accepted'],'gains',gains,flush=True)
    passing=[t for t in trials if t['accepted']];selected=min(passing,key=lambda t:t['arms']['c0']['negative_twice_elbo']) if passing else None
    write(OUT/(case+'.json'),dict(case=case,trials=trials,nulls=nulls,selected=selected,all_original_IDs_and_gate_thresholds_unchanged=True))


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve joint-curve step experiment')
    cases=read(runner.RAW/'protocol.json')['cases'];write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        hypothesis='a shared receiver event can make individually passing curved-source additions mutually compatible',
        maximum_joint_masks_per_case=1,maximum_step_targets=1,
        eligibility='largest failed union of independently paired-valid standalone additions; a new component fails only step in both arms',
        source_and_control_must_pass_existing_every_deletion_curvature_rule=True,
        controls='original parent only, same RX, other families excluding all newly added families,4points each side',
        original300Hz_prior_and_fixed2log_saved_trials_times_source_splits_times2_penalty=True,
        same_mask_unconstrained5x48_null_and_event_fits_cold_in_both_arms=True,
        all_original_gates_and_accepted_IDs_retained=True,no_GPS_following_TLE_new_RF_IQ_or_point_pruning=True))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s joint-event batch cap')));signal.alarm(600)
    for case in cases:one(case)
    signal.alarm(0);write(OUT/'execution.json',dict(all_terminal=True,all_passed=True))


if __name__=='__main__':main()
