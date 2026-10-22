"""Scan-disjoint confirmation of an active-owner support bookkeeping repair.

Only previously rejected proposals that pass every non-owner gate qualify.
No already-valid broad-growth proposal is offered. Current incumbents remain
exact fallbacks, and no accuracy function is imported into this driver.
"""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import run_ds23_dbg01_iteration_004 as study
from audit_ds23_algo01_coverage import retained_metrics
from ds23_active_mode_support import disabled_families
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha
import audit_ds23_family_cavity as auditor

OUT=study.RAW/'owner_only_confirmation19'


def gate_view(p,disabled):
    fields=dict(vars(p));fields.update(state=p.state,calculate=p.calculate,
        conditional_frequency=p.conditional_frequency,supported=[j for j in p.supported if j not in disabled])
    return SimpleNamespace(**fields)


def one(case):
    d=study.engine.current_setup(case);source=study.PRIOR/'single_curve_reentry'/(case+'_positions.json')
    old=read(source);candidates=[];screen=[]
    for number,trial in enumerate(old['trials']):
        if trial['paired_valid']:continue
        mask=np.asarray(trial['mask'],bool);means=np.asarray(trial['means']);checks=[]
        for arm,saved in trial['arms'].items():
            dd=dict(d,node=trial['node'],keep=mask,means=means,entries=trial['entries'])
            p=study.engine.baseline.build(dd,arm,saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
            disabled=disabled_families(p.supported,p.rows,p.slices,p.members,p.scan.tracks,mask,study.engine.support.protected(d))
            if not disabled:break
            delta=abs(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])
            if delta>1e-5:raise ValueError('prior proposal no longer replays under current context')
            metrics=retained_metrics(gate_view(p,disabled),x)
            passing=bool(all(r['compatible'] for r in metrics['tracks']) and
                         all(r['compatible'] for r in saved['linear_gates']) and saved['final_phase_change_s']<=.01)
            checks.append(dict(arm=arm,disabled_new_one_owner_families=disabled,
                passes_all_non_owner_gates=passing,endpoint_replay_difference=delta))
        eligible=bool(len(checks)==2 and all(v['passes_all_non_owner_gates'] for v in checks))
        screen.append(dict(trial_index=number,eligible=eligible,checks=checks))
        if eligible:candidates.append((number,trial))
    candidates.sort(key=lambda r:(-r[1]['added_curved_points'],tuple(a['component'] for a in r[1]['additions'])))
    trials=[];audits=[]
    for number,original in candidates[:2]:
        mask=np.asarray(original['mask'],bool);means=np.asarray(original['means'])
        pair={a:study.engine.support.refit(d,original['node'],mask,a,means) for a in ['c0','fitted_c']}
        repaired=dict(original,arms=pair,paired_valid=bool(valid(pair) and all(v['final_phase_change_s']<=.01 for v in pair.values())),
                      original_trial_index=number)
        trials.append(repaired)
        for arm,saved in pair.items():
            p=study.engine.support.build(d,original['node'],mask,arm,saved['phase_reference'],means)
            x=np.asarray(saved['endpoint_east_north_km']);delta=abs(p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo'])
            if delta>1e-5:raise ValueError('repaired support endpoint fails replay')
            replay=study.engine.support.summary(p,x,d['entries'])
            assert_curved_gate_replay(saved['gates'],replay['gates']);assert_curved_gate_replay(saved['linear_gates'],replay['linear_gates'])
            density=auditor.density(dict(d,keep=mask),p,x,means,d['entries'])
            audits.append(dict(arm=arm,trial_index=number,endpoint_replay_difference=delta,**density))
    passing=[r for r in trials if r['paired_valid']]
    selected=max(passing,key=lambda r:r['added_curved_points']) if passing else None
    record=dict(case=case,status='complete',screen=screen,trials=trials,selected=selected,
        audits=audits,source_sha256=sha(source),source_path=str(source),
        all_original_curved_and_predictive_points_retained=True,
        no_already_valid_proposal_offered=True,RF_selection_frozen_before_geographic_scoring=True)
    write(OUT/(case+'.json'),record)
    print(case,'eligible',len(candidates),'accepted',selected['added_curved_points'] if selected else 0,flush=True)
    return dict(case=case,status='complete',eligible=len(candidates),selected=selected is not None,endpoint_audits=len(audits))


def main():
    study.configure();OUT.mkdir(exist_ok=True)
    cases=[c for c in read(study.PRIOR/'protocol.json')['cases'] if c!='DS23-0322']
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve frozen confirmation')
    record=dict(cases=cases,count=19,engineering_case_excluded='DS23-0322',
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_active_mode_support.py'),
        original19_inputs_and_nominees_frozen_in_previous_confirmation=True,
        same_site_previously_studied_cases_not_untouched_or_new_location_validation=True,
        rule='only old paired-rejected trials that pass every non-owner gate; disable newly active one-owner physical modes; retain every protected incumbent mode',
        maximum_trials_per_case=2,tie_break='most proposed points then component tuple',
        no_already_valid_broad_growth_used=True,exact_incumbent_fallback_for_no_new_paired_valid_repair=True,
        same_original_both_c_arm_priors_gates_observations_and_five48step_cold_fits=True,
        no_GPS_following_TLE_manual_ID_or_new_RF=True)
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=8) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True,
        RF_selection_sealed_before_geographic_scoring=True))


if __name__=='__main__':main()
