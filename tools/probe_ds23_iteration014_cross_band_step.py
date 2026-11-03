"""Test receiver-wide step support across bands, retaining the original event prior."""

from pathlib import Path
import signal
import numpy as np

import probe_ds23_iteration014_step_transfer as binding
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

runner=binding.runner
OUT=runner.RAW/'cross_band_shared_step'


def supporting_curves(target):
    return [r for r in target['independent_original_parent_curves'] if (r['channel']>4)!=(target['channel']>4)
        and r['gain']>0 and r['amplitude_hz']*target['mean_difference_hz']<0]


def build(d,trial,arm,events):
    if trial['model_base']=='support':return binding.support.build(d,trial,arm,trial['arms'][arm]['phase_reference'],events)
    p=binding.support.make_event_problem(d['scan'],trial['node'],np.asarray(trial['mask'],bool),arm,
        np.asarray(trial['arms'][arm]['phase_reference']),d['powers'],np.asarray(trial['means']),d['model'],events)
    return binding.support.attach_event_predictive(p,trial['entries'],d['powers'])


def coverage(d,t,arm,p):
    old=runner.engine.baseline.build;runner.engine.baseline.build=lambda *_:p
    try:return runner.engine.baseline.inventory(dict(d,arms=t['arms']),arm)
    finally:runner.engine.baseline.build=old


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('360s cross-band event cap')));signal.alarm(360)
    binding.configure('support');runner.configure();d=runner.engine.current_setup(case);targets=read(runner.RAW/'step_transfer_diagnostic'/(case+'.json'))['targets']
    prior=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))['trials'];original=read(runner.RAW/case/'inventory.json')['arms'];trials=[];nulls=[]
    for target in targets[:1]:
        controls=supporting_curves(target)
        if not controls:continue
        null=next(t for t in prior if len(t['additions'])==1 and t['additions'][0]['component']==target['component'])
        event=dict(kind='receiver',receiver=target['receiver'],time_s=target['time_s'],sigma_hz=300.)
        penalty=float(2*np.log(max(1,len(target['times'])-7)*2))
        for base in ['default','support']:
            existing=read(runner.RAW/'support_aware_reentry'/(case+'.json'))['trials'] if base=='support' else [null]
            old=next((t for t in existing if t['additions']==null['additions']),None)
            null_arms=old['arms'] if old is not None else {a:binding.support.refit(d,null,a,[]) for a in ['c0','fitted_c']}
            nulls.append(dict(model_base=base,arms=null_arms,node=null['node'],mask=null['mask'],means=null['means'],entries=null['entries'],additions=null['additions'],events=[],reused=old is not None))
            if base=='support':arms={a:binding.support.refit(d,null,a,[event]) for a in ['c0','fitted_c']}
            else:arms={a:binding.default.events.refit(d['scan'],null['node'],np.asarray(null['mask'],bool),a,d['powers'],np.asarray(null['means']),d['model'],[event],null['entries']) for a in ['c0','fitted_c']}
            gains={a:null_arms[a]['negative_twice_elbo']-r['negative_twice_elbo'] for a,r in arms.items()}
            trial=dict(null,model_base=base,kind='receiver',arms=arms,events=[event],null_arms=null_arms,gains=gains,search_penalty=penalty,
                paired_valid=bool(valid(arms)),cross_band_original_parent_support=[r['component'] for r in controls])
            trial['coverage']={a:coverage(d,trial,a,build(d,trial,a,[event])) for a in arms}
            retained={a:set(original[a]['accepted_observation_ids'])<=set(trial['coverage'][a]['accepted_observation_ids']) for a in arms}
            trial['all_original_IDs_preserved']=retained
            trial['accepted']=bool(trial['paired_valid'] and all(s['final_phase_change_s']<=.01 for s in arms.values()) and min(gains.values())>penalty and all(retained.values()))
            trials.append(trial);write(OUT/(case+'_checkpoint.json'),dict(trials=trials,nulls=nulls));print(case,base,'cross-band step accepted',trial['accepted'],'RF gains',gains,flush=True)
    # Prespecified default-first, then existing support simplification. No GPS choice.
    selected=next((t for t in trials if t['accepted']),None)
    write(OUT/(case+'.json'),dict(case=case,trials=trials,nulls=nulls,selected=selected,RF_selection_before_geographic_scoring=True))
    signal.alarm(0)


def main():
    binding.configure('support');OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve cross-band step experiment')
    cases=read(runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        hypothesis='a receiver-wide step can be supported by an original curved family on the other band',
        original013only_step_failure_predicate_and_other_family_same_receiver_control_retained=True,
        new_nomination_scope='other band may support receiver-wide events; it cannot support a band-only event',
        maximum_targets_per_scan=1,maximum_event_times=1,models=['default','support'],selection='first paired passing variant, default before support',
        original300Hz_event_prior_and2log_source_splits_times2_penalty_unchanged=True,
        matched_no_event_null_for_each_identical_mask_and_base=True,
        original5phase48step_cold_fit_and360second_case_cap=True,
        all_original_calibration_and_associated_IDs_must_be_preserved=True,
        no_linear_source_calibration_GPS_following_TLE_new_RF_IQ_or_point_pruning=True))
    for case in cases:one(case)
    write(OUT/'execution.json',dict(all_terminal=True,all_passed=True))


if __name__=='__main__':main()
