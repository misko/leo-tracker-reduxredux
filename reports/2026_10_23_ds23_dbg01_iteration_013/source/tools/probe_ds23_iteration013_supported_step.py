"""Compose the existing support-aware base with the existing shared step term."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

import probe_ds23_iteration013_shared_step as previous
from ds23_active_mode_support import make_problem as support_problem
from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_dsx01_localization_failures import fit
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

runner=previous.runner
OUT=runner.RAW/'supported_shared_step'


def build(d,null,arm,reference,event_list):
    protected=runner.engine.support.protected(d)
    def factory(scan,node,keep,a,r,powers,means,multiplier,nu):
        return support_problem(scan,node,keep,a,r,powers,means,dict(multiplier=multiplier,nu=nu),protected)
    p=make_event_problem(d['scan'],null['node'],np.asarray(null['mask'],bool),arm,np.asarray(reference),d['powers'],np.asarray(null['means']),d['model'],event_list,base_problem_factory=factory)
    attach_event_predictive(p,null['entries'],d['powers']);return previous.events.cached(p)


def refit(d,null,arm,event_list):
    reference=np.zeros(len(null['means']));x=np.zeros(2);history=[]
    for _ in range(5):
        p=build(d,null,arm,reference,event_list);result=fit(p,x,iterations=48);x=np.asarray(result['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
    result=previous.events.summary(p,x,null['entries']);result.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],disabled_shape_families=p.disabled_new_one_owner_orbit_families)
    return result


def one(case):
    runner.configure();d=runner.engine.current_setup(case);old=read(previous.OUT/(case+'.json'));trials=[];nulls=[];checks=[]
    existing=read(runner.RAW/'support_aware_reentry'/(case+'.json'))['trials']
    scopes=[]
    for t in old['trials']:
        if t['additions'] not in scopes:scopes.append(t['additions'])
    for scope in scopes:
        old_rows=[t for t in old['trials'] if t['additions']==scope];null=old_rows[0]
        reused=next((t for t in existing if t['additions']==scope),None)
        null_arms=reused['arms'] if reused else {a:refit(d,null,a,[]) for a in ['c0','fitted_c']}
        for a,s in null_arms.items():
            p=build(d,null,a,s['phase_reference'],[]);delta=p.calculate(np.asarray(s['endpoint_east_north_km']))['negative_twice_elbo']-s['negative_twice_elbo']
            if abs(delta)>1e-5:raise ValueError('support-aware event adapter changed its matched zero-event null')
            checks.append(dict(scope=scope,arm=a,null_replay_difference=delta,reused=reused is not None))
        nulls.append(dict(additions=scope,arms=null_arms,reused=reused is not None))
        for prior in old_rows:
            arms={a:refit(d,null,a,prior['events']) for a in ['c0','fitted_c']};gains={a:null_arms[a]['negative_twice_elbo']-s['negative_twice_elbo'] for a,s in arms.items()}
            accepted=bool(valid(arms) and all(s['final_phase_change_s']<=.01 for s in arms.values()) and min(gains.values())>prior['search_penalty'])
            result=dict(prior,arms=arms,gains=gains,paired_valid=bool(valid(arms)),accepted=accepted,null_arms=null_arms,
                matched_support_null_reused=reused is not None,no_new_orbit_shape_freedom_or_support_gate_relaxation=True)
            trials.append(result);write(OUT/(case+'_checkpoint.json'),dict(trials=trials));print(case,prior['kind'],prior['added_curved_points'],'support-aware accepted',accepted,flush=True)
    write(OUT/(case+'.json'),dict(case=case,trials=trials,nulls=nulls,null_parity_checks=checks,selected=previous.choose(trials),RF_choices_before_geographic_evaluation=True))
    return dict(case=case,trials=len(trials),selected=previous.choose(trials) is not None)


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve supported-step composition')
    cases=read(runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),event_helper_sha256=sha(Path(make_event_problem.__code__.co_filename)),
        previous_default_event_trials_preserved=True,only_support_aware_base_factory_changes=True,
        same_one_shared_event_time_prior_masks_aliases_and_cold5x48budget=True,
        old_original_family_shape_modes_protected_new_one_owner_shape_modes_disabled=True,
        no_gate_threshold_or_physical_prior_scale_relaxation=True,
        zero_event_null_matched_to_support_base_and_existing_fit_reused_where_available=True,
        same_penalty_and_both_arm_RF_gain_acceptance_as_default_shared_step=True,
        no_GPS_following_TLE_new_RF_IQ_or_point_pruning=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
