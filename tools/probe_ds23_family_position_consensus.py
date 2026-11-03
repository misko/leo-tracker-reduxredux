"""Whole-family position sensitivity and three prespecified ensemble estimators.

GPS is absent. Every candidate is checked against the full original curved
and predictive evidence; no failed deletion fit is silently removed.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np

from algo02_scan import pair_passes
from ds23_family_position_consensus import position_candidates
from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context
from probe_ds23_frequency_events import cached,summary
from probe_ds23_symmetric_family_selection import OUT as BANK,bound_incumbent
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_dsx01_clean_region import zero_state

OUT=ROOT/'reports/2026_10_20_ds23_family_position_consensus'
KINDS=('mean','geometric_median','jackknife')
ARMS=('c0','fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (
        ROOT/'tools/probe_ds23_family_position_consensus.py',ROOT/'tools/ds23_family_position_consensus.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen family-position estimators changed')
        return p
    cases=read(BANK/'protocol.json')['cases']
    p=dict(cases=cases,workers=20,source_sha256=hashes(),estimators=KINDS,
        hypothesis='position consistency across independently removed satellite families can expose calibration/identity leverage missed by frequency prediction',
        deletion='every active curved satellite, all its receivers and channels, and its predictive linear factors',
        original_covariance_and_signed_phase_incumbent_unchanged=True,
        cold_start_km=[0,0],box_width_km=25,fold_phase_rounds=5,fold_position_iterations=48,
        minimum_active_families=4,no_deletion_fit_dropped=True,
        qualification='every deletion fit finite, inside original box, phase change <=0.01; candidate full-data original paired gates pass',
        candidate_phase_refreshes_at_fixed_position=5,all_original_observations_restored_for_candidate_checks=True,
        no_in_sample_RF_improvement_required_for_bias_corrected_estimator=True,
        jackknife_not_proven_unbiased_for_heterogeneous_geometry=True,
        three_estimators_are_separate_prespecified_policies_not_GPS_selected=True,
        same_masks_labels_aliases_powers_priors_and_budgets_between_c_arms=True,
        no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True,
        development_cohort_previously_exposed=True)
    write(path,p);return p


def setup(case):
    scan,node,keep,base,old=context(case);bank=read(BANK/case/'result.json');signed,binding=bound_incumbent(case)
    if bank['incumbent_arms']!=signed['policy_arms']:raise ValueError('signed reference changed')
    node=dict(node,seed=dict(node['seed'],state=zero_state(scan)))
    return scan,node,keep,base,old,np.asarray(bank['powers']),np.asarray(bank['means_s'])[base.labels],signed['policy_arms'],binding


def make(scan,node,keep,arm,reference,powers,means,model,entries):
    p=make_event_problem(scan,node,keep,arm,reference,powers,means,model,[])
    attach_event_predictive(p,entries,powers);cached(p);return p


def plan(case):
    directory=OUT/case;directory.mkdir(exist_ok=True);path=directory/'plan.json'
    if path.exists():return read(path)
    scan,node,keep,base,old,powers,means,incumbent,binding=setup(case)
    labels=np.asarray(base.labels)[base.flat_labels]
    families=sorted(set(labels[keep].tolist()))
    p=dict(case=case,families=families,mask=keep,
        incumbent_binding=binding,bank_result_sha256=sha(BANK/case/'result.json'),
        active_curved_points=int(keep.sum()),minimum_family_count_met=len(families)>=4)
    write(path,p);return p


def fold_job(case,family):
    path=OUT/case/f'without_{family}.json'
    if path.exists():return dict(case=case,family=family,cached=True)
    scan,node,keep,base,old,powers,means,incumbent,binding=setup(case)
    labels=np.asarray(base.labels)[base.flat_labels];train=keep&(labels!=family)
    if not train.any() or np.any(train&(labels==family)):raise ValueError('invalid family deletion')
    original_entries=old['linear_entries'] if old['linear_paired_valid'] else []
    entries=[e for e in original_entries if e['candidate_index']!=family]
    pair={}
    for arm in ARMS:
        x=np.zeros(2);reference=np.zeros(len(means));history=[]
        for epoch in range(5):
            p=make(scan,node,train,arm,reference,powers,means,old['hyperparameters_from_pre_RF_TLE_only'],entries)
            fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
            phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            change=float(np.max(abs(phase-reference)))
            history.append(dict(epoch=epoch,endpoint_east_north_km=x,phase_change_s=change));reference=phase
        pair[arm]=dict(endpoint_east_north_km=x,history=history,phase_reference=p.reference,
                       final_phase_change_s=change,negative_twice_elbo=p.calculate(x)['negative_twice_elbo'])
    record=dict(case=case,held_family_index=family,held_norad=int(scan.norads[family]),arms=pair,
        train_curved_points=int(train.sum()),train_predictive_points=sum(e['points'] for e in entries),
        no_held_family_in_curved_or_predictive_training=True,
        qualified=all(r['final_phase_change_s']<=.01 and np.isfinite(r['endpoint_east_north_km']).all()
                      and np.max(abs(r['endpoint_east_north_km']))<=12.5+1e-8 for r in pair.values()))
    write(path,record);return dict(case=case,family=family,qualified=record['qualified'])


def finalize(case):
    declaration=plan(case);scan,node,keep,base,old,powers,means,incumbent,binding=setup(case)
    if sha(BANK/case/'result.json')!=declaration['bank_result_sha256']:raise ValueError('consensus inputs changed')
    folds=[read(OUT/case/f'without_{j}.json') for j in declaration['families']]
    supported=len(folds)>=4 and all(f['qualified'] for f in folds)
    candidate_positions={a:position_candidates(incumbent[a]['endpoint_east_north_km'],
        [f['arms'][a]['endpoint_east_north_km'] for f in folds]) for a in ARMS} if len(folds)>=4 else {}
    entries=old['linear_entries'] if old['linear_paired_valid'] else [];policies={}
    for kind in KINDS:
        pair={};reason=None
        if not supported:reason='insufficient families or at least one deletion fit failed convergence/domain checks'
        elif any(np.max(abs(candidate_positions[a][kind]))>12.5 for a in ARMS):reason='ensemble position outside original regional box'
        else:
            for arm in ARMS:
                x=np.asarray(candidate_positions[arm][kind]);reference=np.zeros(len(means));history=[]
                for epoch in range(5):
                    p=make(scan,node,keep,arm,reference,powers,means,old['hyperparameters_from_pre_RF_TLE_only'],entries)
                    phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                    change=float(np.max(abs(phase-reference)));history.append(dict(epoch=epoch,phase_change_s=change));reference=phase
                pair[arm]=dict(summary(p,x,entries),history=history,final_phase_change_s=change)
        valid=bool(pair and pair_passes(pair,include_linear=True))
        policies[kind]=dict(accepted=valid,trial_arms=pair,policy_arms=pair if valid else incumbent,rejection_reason=reason)
    result=dict(case=case,policies=policies,incumbent_arms=incumbent,baseline_arms=old['policy_arms'],
        candidate_positions=candidate_positions,all_deletion_fits_qualified=supported,
        held_family_count=len(folds),GPS_used=False,future_TLE_used=False,
        every_original_observation_reinstated_in_final_gate_replay=True,
        source_sha256=hashes())
    write(OUT/case/'result.json',result)
    print(case,'consensus accepted',{k:r['accepted'] for k,r in policies.items()},flush=True)
    return dict(case=case,accepted={k:r['accepted'] for k,r in policies.items()})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args();protocol=prepare()
    cases=[args.case] if args.case else protocol['cases'];tasks=[]
    for case in cases:tasks.extend((case,j) for j in plan(case)['families'])
    receipts=[]
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        futures={pool.submit(fold_job,*task):task for task in tasks}
        for f in as_completed(futures):
            try:receipts.append(f.result())
            except Exception as exc:receipts.append(dict(task=futures[f],error=repr(exc)))
            write(OUT/('fold_progress_'+(args.case or 'cohort')+'.json'),dict(completed=len(receipts),total=len(tasks),receipts=receipts))
    errors=[r for r in receipts if 'error' in r]
    final=[finalize(c) for c in cases] if not errors else []
    write(OUT/('execution_'+(args.case or 'cohort')+'.json'),dict(all_terminal=True,receipts=receipts,errors=errors,final=final))
