"""Existing-family replacement after native predictive evidence is recovered.

Pick the family with the most newly recovered persistent points, using RF IDs
alone. Exclude its complete curved evidence during catalogue nomination. Keep
all old and new observations for the paired, same-mask final comparison.
"""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import copy
import signal
import numpy as np

import probe_ds23_iteration017_recovery as binding
import probe_ds23_family_cavity_nominations as cavity
from ds23_family_cavity import coarse_phase_scores,unused_student_gap
from probe_ds23_family_cavity_position import configuration,fit_configuration,unused_count
from audit_ds23_iteration013_recovery import check
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha

OUT=binding.runner.RAW/'native_augmented_family_v2'


def choose_family(new_entries,active):
    counts={}
    for entry in new_entries:
        j=entry['candidate_index']
        if j in active:counts[j]=counts.get(j,0)+entry['points']
    return min(counts,key=lambda j:(-counts[j],j)) if counts else None


def family_evidence(data,target):
    held=cavity.family_data(data,target)
    held['target']=target
    return held


def parent(case):
    binding.configure('paths');paths=binding.paths.paths
    data,coverage,kind,_=paths.parent(case)
    if kind!='default':raise ValueError('native-family experiment requires an explicit support-parent adapter')
    source=read(binding.runner.RAW/'graph_seeded_paths'/(case+'.json'))['methods']['persistent5s']
    if not source.get('accepted'):return data,coverage,[]
    selected=read(binding.runner.RAW/'graph_seeded_paths'/(case+'_persistent5s_selection.json'))['selected']
    scan,entries=paths.native.append_native_paths(data['scan'],data['entries'],selected,paths.native.receiver_basis(data['scan']))
    return dict(data,scan=scan,entries=entries,arms=source['arms']),source['coverage'],entries[len(data['entries']):]


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('360s native-family experiment cap')));signal.alarm(360)
    data,old_coverage,new_entries=parent(case)
    active={r['candidate_index'] for r,sl in zip(data['base'].rows,data['base'].slices,strict=True) if data['keep'][sl].any()}
    target=choose_family(new_entries,active);result=dict(case=case,status='complete',eligible=target is not None,trials=[],selected=None)
    if target is not None:
        saved=data['arms']['c0'];data=dict(data,x=np.asarray(saved['endpoint_east_north_km']),reference=np.asarray(saved['phase_reference']))
        held=family_evidence(data,target)
        frequency,elevation=phase_frequency_grid(data['scan'].sky,held['times'],*latlon(data['x']),phase_seconds=data['all_means'])
        plus=phase_frequency_grid(data['scan'].sky,held['times'],*latlon(data['x']),phase_seconds=data['all_means']+.01)[0]
        minus=phase_frequency_grid(data['scan'].sky,held['times'],*latlon(data['x']),phase_seconds=data['all_means']-.01)[0]
        coarse=coarse_phase_scores(held['values'],held['radio']@held['coefficient'][:held['radio_width']],held['q']*frequency,
            held['q']*(plus-minus)/.02,data['widths'],held['base_covariance'],held['groups'])
        scores=np.where(elevation.min(axis=1)>=0,coarse['score'],np.inf)
        pool=[int(j) for j in np.argsort(scores) if np.isfinite(scores[j])][:7]
        if target not in pool:pool.append(target)
        nominations=sorted([cavity.candidate_prediction(data,held,j,coarse['aliases'][j]) for j in pool],key=lambda r:r['score'])
        alternatives=[r for r in nominations if r['candidate_index']!=target and r['qualified']]
        offers=alternatives[:1]
        result.update(target_index=target,target_norad=int(data['scan'].norads[target]),nominations=nominations,
            held_members=held['members'],held_IDs=held['held_ids'],cavity_calibration_mask=held['calibration_mask'],
            new_target_points=sum(e['points'] for e in new_entries if e['candidate_index']==target),
            parent_arms=data['arms'],parent_coverage=old_coverage)
        write(OUT/(case+'_RF_nominations.json'),dict(result,RF_nomination_frozen_before_any_new_position_fit=True))
        null=copy.deepcopy(data['arms'])
        for arm,s in null.items():
            p=binding.runner.engine.baseline.build(data,arm,s['phase_reference'])
            s['corrected_selection_loss']=s['negative_twice_elbo']-unused_count(p,data['entries'])*unused_student_gap(data['model']['nu'])
        audits=[]
        for arm,s in null.items():audits.append(check(data,binding.runner.engine.baseline.build(data,arm,s['phase_reference']),arm,s,'native_family_null'))
        for offer in offers:
            family=dict(original_index=target,members=held['members'])
            node,entries,means=configuration(data,[(family,offer)])
            trial=fit_configuration(data,node,entries,means)
            changed=dict(data,node=node,entries=entries,means=means,arms=trial['arms'])
            coverage={a:binding.paths.paths.coverage(changed,'default',a,s) for a,s in trial['arms'].items()}
            for arm,s in trial['arms'].items():audits.append(check(changed,binding.runner.engine.baseline.build(changed,arm,s['phase_reference']),arm,s,'native_family_alternative'))
            gains={a:null[a]['corrected_selection_loss']-trial['arms'][a]['corrected_selection_loss'] for a in null}
            retained={a:set(old_coverage[a]['accepted_observation_ids'])<=set(coverage[a]['accepted_observation_ids']) for a in null}
            trial.update(candidate_norad=offer['norad'],RF_gains=gains,search_penalty=float(2*np.log(2)),coverage=coverage,
                all_parent_accepted_IDs_preserved=retained,mask=data['keep'],
                accepted=bool(trial['paired_valid'] and min(gains.values())>2*np.log(2) and all(retained.values())))
            result['trials'].append(trial)
            if trial['accepted']:result['selected']=trial
            print(case,'native family',result['target_norad'],'alternative',offer['norad'],'gains',gains,'accepted',trial['accepted'],flush=True)
        result.update(null_arms=null,independent_endpoint_checks=audits)
    write(OUT/(case+'.json'),result);signal.alarm(0)
    return dict(case=case,status='complete',eligible=target is not None,accepted=result['selected'] is not None)


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve native-family experiment')
    cases=read(binding.runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        hypothesis='new persistent owner evidence can test an original influential family identity without GPS deletion',
        target_rule='most newly recovered persistent predictive points among existing curved families; ties candidate index',
        target_rule_has_no_GPS_or_family_deletion_error_input=True,
        parent='original qualified persistent5s result; same frozen original+native IDs in null and alternative',
        original_whole_family_curved_data_excluded_from_nomination_calibration=True,
        all_causal_candidates_coarse_then_best7_and_original_refined=True,
        one_best_phase_qualified_alternative_gets_original5x48_and_near_feasible5x40_budget=True,
        null_reuses_qualified_native_endpoint_with_independent_replay=True,
        accepted_only_paired_RF_gain_above2log2_all_original_gates_and_all_parent_accepted_IDs=True,
        c0_and_fitted_c_match_observations_identities_aliases_priors_and_budgets=True,
        no_new_calibration_points_mode_coordinates_or_noise_parameters=True,
        no_GPS_following_TLE_new_RF_IQ_or_point_pruning=True,
        engineering2_only_no_full_DS23_or_new_location_claim=True,workers=2,per_case_seconds=360))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
