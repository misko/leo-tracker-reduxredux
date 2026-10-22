"""Apply existing bounded residual-constrained refinement to supported reentry."""

import copy
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import run_ds23_dbg01_iteration_006 as runner
import audit_ds23_family_cavity as density_audit
from ds23_feasible_position import feasible_fit
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import summary
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'supported_feasibility'


def near_feasible(paired_slacks):
    values=np.array([v for slacks in paired_slacks.values() for v in slacks.values()])
    return bool(len(paired_slacks)==2 and len(values) and np.isfinite(values).all() and -.25<=values.min()<0)


def all_slacks(p,x,entries):
    result=gate_slacks(p,x,entries)
    for index,value in enumerate(p.state(x)['phases']):
        if value!=0:result['phase/'+str(index)]=1-abs(float(value))/15.
    return result


def build(d,trial,arm,reference):
    return runner.engine.support.build(d,trial['node'],np.asarray(trial['mask'],bool),arm,reference,np.asarray(trial['means']))


def refine(d,trial,arm):
    start=trial['arms'][arm];x=np.asarray(start['endpoint_east_north_km']);reference=np.asarray(start['phase_reference']);history=[]
    for epoch in range(5):
        p=build(d,trial,arm,reference)
        result=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
            lambda z:list(all_slacks(p,z,d['entries']).values()),x,p.lower,p.upper,iterations=40)
        x=np.asarray(result['parameters']);phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(np.max(abs(phase-reference)))))
        reference=phase
    saved=summary(p,x,d['entries']);saved.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
        disabled_shape_families=p.disabled_new_one_owner_orbit_families,minimum_constraint_slack=min(all_slacks(p,x,d['entries']).values()))
    return saved


def audit(d,trial):
    checks=[]
    for arm,saved in trial['arms'].items():
        p=build(d,trial,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km']);replay=summary(p,x,d['entries'])
        delta=replay['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-5:raise ValueError('constrained support endpoint does not replay')
        assert_curved_gate_replay(saved['gates'],replay['gates']);assert_curved_gate_replay(saved['linear_gates'],replay['linear_gates'])
        checks.append(dict(arm=arm,endpoint_difference=delta,**density_audit.density(d,p,x,np.asarray(trial['means']),d['entries'])))
    return checks


def one(case):
    path=OUT/(case+'.json')
    if path.exists():return dict(case=case,cached=True)
    d=runner.engine.current_setup(case);original=read(runner.RAW/'support_aware_reentry'/(case+'.json'))
    proposals=[];diagnostics=[];trials=[]
    for trial in original['trials']:
        slacks={a:all_slacks(build(d,trial,a,r['phase_reference']),np.asarray(r['endpoint_east_north_km']),d['entries']) for a,r in trial['arms'].items()}
        eligible=near_feasible(slacks) and not trial['paired_valid']
        diagnostics.append(dict(additions=trial['additions'],paired_slacks=slacks,eligible=eligible))
        if eligible:proposals.append(trial)
    write(OUT/(case+'_selection.json'),dict(case=case,diagnostics=diagnostics,
        selected_components=[[a['component'] for a in t['additions']] for t in proposals[:2]],
        frozen_before_new_fit=True,no_geographic_score_used=True))
    for proposal in proposals[:2]:
        trial=copy.deepcopy(proposal);trial['arms']={a:refine(d,proposal,a) for a in ['c0','fitted_c']}
        trial['paired_valid']=bool(valid(trial['arms']));trial['checks']=audit(d,trial);trials.append(trial)
        print(case,'supported feasible',trial['added_curved_points'],trial['paired_valid'],flush=True)
    good=[t for t in trials if t['paired_valid']]
    if len(good)==2 and not ({a['component'] for a in good[0]['additions']}&{a['component'] for a in good[1]['additions']}):
        additions=good[0]['additions']+good[1]['additions'];node=copy.deepcopy(d['node']);mask=d['keep'].copy()
        for a in additions:
            k=next(k for k,row in enumerate(node['seed']['rows']) if row['component']==a['component'])
            node['seed']['rows'][k].update(candidate_index=a['candidate_index'],candidate_norad=a['norad'])
            node['aliases'][k]=a['alias'];mask[d['base'].slices[k]]=True
        labels=sorted({r['candidate_index'] for r in node['seed']['rows']});means=d['all_means'][labels]
        trial=dict(node=node,mask=mask,means=means,entries=d['entries'],additions=additions,added_curved_points=int(mask.sum()-d['keep'].sum()))
        trial['arms']={a:runner.engine.support.refit(d,node,mask,a,means) for a in ['c0','fitted_c']}
        slacks={a:all_slacks(build(d,trial,a,r['phase_reference']),np.asarray(r['endpoint_east_north_km']),d['entries']) for a,r in trial['arms'].items()}
        if not valid(trial['arms']) and near_feasible(slacks):trial['arms']={a:refine(d,trial,a) for a in ['c0','fitted_c']}
        trial['paired_valid']=bool(valid(trial['arms']));trial['checks']=audit(d,trial);trials.append(trial)
        if trial['paired_valid']:good.append(trial)
        print(case,'disjoint union',trial['added_curved_points'],trial['paired_valid'],flush=True)
    selected=max(good,key=lambda t:t['added_curved_points']) if good else None
    write(path,dict(case=case,trials=trials,selected=selected,
        selection='maximum new whole-track points among paired-valid bounded trials; no cross-mask loss comparison',
        source_sha256=sha(Path(__file__)),RF_selection_complete_before_geographic_scoring=True))
    return dict(case=case,accepted=selected is not None,additional_points=selected['added_curved_points'] if selected else 0)


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    record=dict(cases=read(runner.RAW/'protocol.json')['cases'],maximum_candidates_per_case=2,one_disjoint_valid_union=True,
        original_supported_mode_hypotheses_and_aliases_frozen=True,minimum_initial_slack=-.25,
        refinement_rounds=5,iterations_per_round=40,all_original_residual_gates_plus_existing15s_phase_gate=True,
        no_new_prior_or_nuisance_coordinate_or_point_trim=True,no_GPS_or_following_TLE=True,
        matched_c_arms=True,source_sha256=sha(Path(__file__)))
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve feasibility experiment')
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,record['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,no_geographic_scoring_yet=True))


if __name__=='__main__':main()
