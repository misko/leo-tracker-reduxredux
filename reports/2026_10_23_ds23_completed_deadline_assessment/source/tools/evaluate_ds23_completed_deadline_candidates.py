"""Seal fresh-audited deadline decisions, then evaluate every available DS23 case."""

import argparse
from pathlib import Path
import numpy as np

import inventory_ds23_completed_deadline_candidates as study
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=study.OUT/'evaluation'
ORIGINAL=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_007_raw/new_family_evaluation'


def select():
    OUT.mkdir(exist_ok=True)
    if (OUT/'RF_selection.json').exists():raise FileExistsError('preserve finalized deadline choices')
    inventory=read(study.OUT/'RF_inventory.json');execution=read(study.OUT/'fresh_audit/execution.json')
    if not execution['all_terminal']:raise ValueError('wait for terminal native audits')
    rows=[]
    for r in inventory['rows']:
        audit_path=study.OUT/'fresh_audit'/(r['case']+'.json');accepted=False;audit_sha=None
        if r['eligible_pending_fresh_audit']:
            a=read(audit_path);audit_sha=sha(audit_path);accepted=bool(a['all_passed'])
            if accepted and a['source_sha256']!=r['source_sha256']:raise ValueError('audited deadline source differs')
        rows.append(dict(case=r['case'],accepted=accepted,trial_index=r['tentative_selected_index'] if accepted else None,
            source_sha256=r['source_sha256'],canonical_source_sha256=r['canonical_source_sha256'],audit_sha256=audit_sha))
    write(OUT/'RF_selection.json',dict(rows=rows,all410included=True,source_sha256=sha(Path(__file__)),
        RF_selection_frozen_before_geographic_evaluation=True,no_new_fit_or_GPS_choice=True,
        same_deadline_search_budget_with_original_fallback_for_every_unqualified_case=True,
        inventory_sha256=sha(study.OUT/'RF_inventory.json')))
    print('RF-frozen deadline rescues',[r['case'] for r in rows if r['accepted']],flush=True)


def evaluate():
    selection=read(OUT/'RF_selection.json');assert selection['RF_selection_frozen_before_geographic_evaluation']
    if (OUT/'evaluation.json').exists():raise FileExistsError('preserve complete-population deadline evaluation')
    from report_algo02_ds23 import position_error
    old=read(ORIGINAL/'evaluation.json');baseline={(r['case'],r['arm']):r for r in old['rows'] if r['method']=='incumbent'};rows=[]
    for choice in selection['rows']:
        case=choice['case'];canonical_path=study.reference.SOURCE/(case+'.json')
        if sha(canonical_path)!=choice['canonical_source_sha256']:raise ValueError('canonical source changed after selection')
        canonical=read(canonical_path);decision=study.reference.decisions(canonical);arms=canonical['trials'][decision['best_paired_trial_index']]['arms'] if decision['accepted']['published_c0_positive'] else canonical['baseline_arms']
        if choice['accepted']:
            source=study.SOURCE/'reentry'/(case+'.json')
            if sha(source)!=choice['source_sha256']:raise ValueError('deadline source changed after selection')
            trial=read(source)['trials'][choice['trial_index']];audit_path=study.OUT/'fresh_audit'/(case+'.json')
            if sha(audit_path)!=choice['audit_sha256']:raise ValueError('native audit changed after selection')
            audit=read(audit_path);old_cov=read(ORIGINAL/'cases'/(case+'.json'))['coverage']
        for arm,original in arms.items():
            reference=baseline[case,arm];old_error=position_error(original['endpoint_latlon'])
            if abs(old_error-reference['position_error_km'])>1e-8:raise ValueError('original410 population no longer reproduces')
            candidate=trial['arms'][arm] if choice['accepted'] else original
            cov=audit['coverage'][arm] if choice['accepted'] else None
            if cov and not set(old_cov[arm+'_incumbent']['accepted_observation_ids'])<=set(cov['accepted_observation_ids']):raise ValueError('deadline candidate loses independently archived parent membership')
            for method,fit,coverage in [('Incumbent',original,None),('Completed deadline candidate',candidate,cov)]:
                error=position_error(fit['endpoint_latlon']);associated=coverage['associated'] if coverage else reference['associated_points']
                rows.append(dict(case=case,arm=arm,method=method,accepted_rescue=bool(choice['accepted'] and method!='Incumbent'),
                    error_km=error,original_error_km=old_error,error_change_km=error-old_error,associated_points=associated,total_GLRT=reference['total_GLRT'],
                    associated_percent=100*associated/reference['total_GLRT'],curved_points=fit['active_points'],predictive_points=fit.get('predictive_points',reference['predictive_points']),
                    RMS_hz=fit['RMS_hz'],original_IDs_lost=0))
    summary=[]
    for arm in ['c0','fitted_c']:
        for method in ['Incumbent','Completed deadline candidate']:
            rr=[r for r in rows if r['arm']==arm and r['method']==method];err=np.array([r['error_km'] for r in rr]);delta=np.array([r['error_change_km'] for r in rr]);total=sum(r['total_GLRT'] for r in rr);associated=sum(r['associated_points'] for r in rr)
            summary.append(dict(arm=arm,method=method,cases=len(rr),rescued_cases=sum(r['accepted_rescue'] for r in rr),mean_error_km=float(err.mean()),median_error_km=float(np.median(err)),
                p90_error_km=float(np.quantile(err,.9)),maximum_error_km=float(max(err)),within0p5km=int(sum(err<=.5)),improved=int(sum(delta< -1e-6)),worsened=int(sum(delta>1e-6)),
                regressions_over500m=int(sum(delta>.5)),associated_points=associated,total_GLRT=total,associated_percent=100*associated/total,
                mean_RMS_hz=float(np.mean([r['RMS_hz'] for r in rr]))))
    import report_ds23_dbg01_iteration_001 as f
    f.csv_write(OUT/'positions.csv',rows);f.csv_write(OUT/'summary.csv',summary)
    write(OUT/'evaluation.json',dict(rows=rows,summary=summary,all410available_retained=True,unavailable=['DS23-0012','DS23-0184','DS23-0286'],
        canonical_baseline_reproduced=True,RF_selection_sha256=sha(OUT/'RF_selection.json'),no_new_ALGO_or_new_location_claim=True))
    print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['select','evaluate'],required=True);args=parser.parse_args()
    select() if args.stage=='select' else evaluate()
