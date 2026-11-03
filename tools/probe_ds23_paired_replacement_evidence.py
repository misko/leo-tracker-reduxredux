"""Matched410-scan decision replay: require RF gains in both calibration arms.

No fitting or geographic scoring occurs in the selection stage. All candidates,
observations, physical priors and numerical endpoints are the published ones.
"""

import argparse
from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha
from audit_ds23_archived_qualification import qualification

SOURCE=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23/position'
AUTHORITY=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/evidence/publication_receipt.json'
OUT=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_011_raw/paired_replacement_evidence'
METHODS=('published_c0_positive','paired_positive','paired_2log2_margin','published_sticky_control')


def decisions(record):
    eligible=[i for i,t in enumerate(record['trials']) if t['paired_valid']]
    best=min(eligible,key=lambda i:record['trials'][i]['arms']['c0']['corrected_selection_loss']) if eligible else None
    gains={a:record['baseline_corrected_loss'][a]-record['trials'][best]['arms'][a]['corrected_selection_loss'] for a in ['c0','fitted_c']} if best is not None else None
    positive=bool(gains is not None and gains['c0']>0)
    flags=dict(published_c0_positive=positive,
        paired_positive=bool(positive and gains['fitted_c']>0),
        paired_2log2_margin=bool(gains is not None and min(gains.values())>2*np.log(2)),
        published_sticky_control=bool(gains is not None and gains['c0']>record['search_penalty']))
    return dict(best_paired_trial_index=best,RF_gains=gains,accepted=flags)


def select():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve frozen full-population decision replay')
    authority=read(AUTHORITY);bindings=authority['case_result_sha256'];cases=sorted(r['case'] for r in bindings)
    if len(cases)!=410:raise ValueError('published available population differs')
    protocol=dict(cases=cases,dataset_total=413,unavailable=['DS23-0012','DS23-0184','DS23-0286'],
        primary='paired_positive',control='paired_2log2_margin',reproduced_controls=['published_c0_positive','published_sticky_control'],
        c0_best_trial_is_identical_in_all_rules_no_candidate_reranking=True,
        primary_rule='same c0-best passing hypothesis must improve normalized RF evidence in both c0 and fitted-c',
        fixed_margin_control=float(2*np.log(2)),margin_not_tuned_or_swept_using_GPS=True,
        original_combined_recovery_requires_positive_fitted_c_same_mask_gain=True,
        existing_rule_source_sha256=sha(ROOT/'tools/run_ds23_combined_recovery_full.py'),
        all_masks_values_candidates_aliases_powers_physical_priors_and_fit_budgets_identical=True,
        cached_audited_endpoint_selection_replay_not_new_acquisition_or_position_fits=True,
        no_GPS_following_TLE_new_RF_or_point_selection=True,
        both_c_arms_shared_decision=True,saved_gate_qualification_reported_for_each_returned_arm=True,
        prior_0080_regression_used_to_motivate_rule_development_not_an_untouched_validation=True,
        full_DS23_previously_studied_same_site_not_new_location_evidence=True,
        authority_sha256=sha(AUTHORITY),source_sha256=sha(Path(__file__)))
    write(OUT/'protocol.json',protocol);rows=[]
    for binding in bindings:
        case=binding['case'];path=SOURCE/(case+'.json')
        if sha(path)!=binding['position_sha256']:raise ValueError('published source changed')
        saved=read(path);decision=decisions(saved);qualifications={}
        for method,accepted in decision['accepted'].items():
            arms=saved['trials'][decision['best_paired_trial_index']]['arms'] if accepted else saved['baseline_arms']
            qualifications[method]={a:qualification(r) for a,r in arms.items()}
        rows.append(dict(case=case,source_sha256=sha(path),qualification=qualifications,**decision))
    write(OUT/'RF_selection.json',dict(rows=rows,all410included=True,RF_choices_frozen_before_new_geographic_evaluation=True,
        no_position_refit_or_additional_candidate_search=True,protocol_sha256=sha(OUT/'protocol.json')))
    print('Frozen410 RF decisions', {m:sum(r['accepted'][m] for r in rows) for m in METHODS},flush=True)


def evaluate():
    frozen=read(OUT/'RF_selection.json');assert frozen['RF_choices_frozen_before_new_geographic_evaluation']
    if (OUT/'evaluation.json').exists():raise FileExistsError('preserve geographic evaluation')
    from report_algo02_ds23 import position_error
    import csv
    benchmark=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/tables/positions.csv'
    reference={(r['case'],r['arm']):float(r['policy_error_km']) for r in csv.DictReader(benchmark.open()) if r['policy']=='equal_assignment_priors'}
    rows=[]
    for choice in frozen['rows']:
        path=SOURCE/(choice['case']+'.json')
        if sha(path)!=choice['source_sha256']:raise ValueError('sealed RF source changed')
        saved=read(path);best=saved['trials'][choice['best_paired_trial_index']] if choice['best_paired_trial_index'] is not None else None
        for method,accepted in choice['accepted'].items():
            for arm,r in (best['arms'] if accepted else saved['baseline_arms']).items():
                error=position_error(r['endpoint_latlon']);expected=reference[choice['case'],arm]
                if method=='published_c0_positive' and abs(error-expected)>1e-8:raise ValueError('published benchmark did not reproduce')
                rows.append(dict(case=choice['case'],method=method,arm=arm,accepted_replacement=accepted,
                    position_error_km=error,published_error_km=expected,error_change_km=error-expected,
                    RMS_hz=r['RMS_hz'],qualified=choice['qualification'][method][arm]['qualified'],
                    c0_RF_gain=choice['RF_gains']['c0'] if choice['RF_gains'] else None,
                    fitted_c_RF_gain=choice['RF_gains']['fitted_c'] if choice['RF_gains'] else None))
    summary=[]
    for method in METHODS:
        for arm in ['c0','fitted_c']:
            selected=[r for r in rows if r['method']==method and r['arm']==arm];errors=np.array([r['position_error_km'] for r in selected]);delta=np.array([r['error_change_km'] for r in selected])
            summary.append(dict(method=method,arm=arm,cases=len(selected),replacements=sum(r['accepted_replacement'] for r in selected),
                mean_error_km=float(errors.mean()),median_error_km=float(np.median(errors)),p90_error_km=float(np.quantile(errors,.9)),maximum_error_km=float(errors.max()),
                within0p5km=int((errors<=.5).sum()),qualified=sum(r['qualified'] for r in selected),
                improved_vs_published=int((delta< -1e-6).sum()),worsened_vs_published=int((delta>1e-6).sum()),
                regressions_over500m=int((delta>.5).sum()),mean_RMS_hz=float(np.mean([r['RMS_hz'] for r in selected]))))
    import report_ds23_dbg01_iteration_001 as f
    f.csv_write(OUT/'positions.csv',rows);f.csv_write(OUT/'summary.csv',summary)
    write(OUT/'evaluation.json',dict(rows=rows,summary=summary,RF_selection_sha256=sha(OUT/'RF_selection.json'),
        all_available410_cases_retained=True,published_control_reproduced=True,
        no_new_position_fit_or_new_location_validation=True,source_sha256=sha(Path(__file__))))
    print(summary,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['select','evaluate'],required=True);args=parser.parse_args()
    select() if args.stage=='select' else evaluate()


if __name__=='__main__':main()
