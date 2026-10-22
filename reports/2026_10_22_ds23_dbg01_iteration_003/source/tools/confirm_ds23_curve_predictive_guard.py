"""Scan-disjoint confirmation of iteration003's frozen RF-only growth guard.

Use the already frozen random20 list. No accuracy function is imported here.
No-proposal scans retain the exact published incumbent and remain in evaluation.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import probe_ds23_all_curve_families as growth
import probe_ds23_family_predictive_guard as guard
import run_ds23_dbg01_iteration_002 as context
from run_algo01_ds23_sample import ROOT, read, write, sha

PARENT = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_003_raw'
RAW = ROOT/'reports/2026_10_22_ds23_curve_guard_confirmation_raw'


def proposal_jobs(cases, proposals, families):
    """Schedule folds only for proposals; never remove fallback scans."""
    return [(c, j, v) for c in cases if proposals[c] is not None
            for j in sorted(families[c]) for v in ['baseline', 'expanded']]


def configure():
    context.RAW = RAW
    context.configure()
    growth.configure(RAW)
    guard.RAW = RAW


def protocol():
    RAW.mkdir(parents=True, exist_ok=True)
    source = PARENT/'family_predictive_guard/protocol.json'
    frozen = read(source)
    record = dict(cases=frozen['confirmation_cases'], seed=frozen['confirmation_seed'],
        parent_protocol_sha256=sha(source), source_sha256=sha(Path(__file__)),
        source_hashes={Path(m.__file__).name:sha(Path(m.__file__)) for m in [growth,guard,context,context.reentry]},
        policy='same initial three-curve reentry, eight common-family groups, up to three unions, frozen family predictive guard',
        no_proposal_or_guard_rejection='exact published incumbent, included in all20 denominator',
        matched_c_arms_and_original_priors_gates_and_budgets=True,
        inference_no_GPS_or_following_TLE_or_manual_identity_choice=True,
        no_new_RF_or_IQ_reprocessing_or_stationary_pooling=True,
        same_dataset_and_site_not_untouched_or_new_location_validation=True,
        confirmation_list_frozen_before_development_fold_scores=True,
        guard_rule=frozen['guard'], maximum_workers=24)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen confirmation protocol')
    else:write(path,record)
    folder=RAW/'single_curve_reentry';folder.mkdir(exist_ok=True)
    sub=dict(parent_protocol_sha256=sha(path), reuse='unchanged single-curved reentry nominate and positions functions',
             source_sha256=sha(Path(context.reentry.__file__)))
    if (folder/'protocol.json').exists():
        if read(folder/'protocol.json')!=sub:raise ValueError('single-curve source changed')
    else:write(folder/'protocol.json',sub)
    return record


def run_one(job):
    case,stage=job
    if stage=='inventory':return context.baseline.one(case,stage)
    return context.reentry.one(case,stage)


def folds_setup(cases):
    proposals={c:read(RAW/'all_curve_families'/(c+'_positions.json'))['selected'] for c in cases}
    families={}
    for case in cases:
        d=context.current_setup(case)
        families[case]={r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    out=RAW/'family_predictive_guard';out.mkdir(exist_ok=True)
    source=read(PARENT/'family_predictive_guard/protocol.json')
    record=dict(parent_rule_protocol_sha256=sha(PARENT/'family_predictive_guard/protocol.json'),
        all_confirmation_cases=cases, cases_with_proposals=[c for c in cases if proposals[c] is not None],
        cases_without_proposals=[c for c in cases if proposals[c] is None],
        source_sha256=sha(Path(guard.__file__)), guard=source['guard'],
        no_guard_threshold_or_prior_tuning_on_confirmation=True,
        no_GPS_or_following_TLE_or_manual_identity_choice=True)
    path=out/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen confirmation folds')
    else:write(path,record)
    return proposal_jobs(cases,proposals,families),proposals


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['inventory','nominations','positions','audit','folds','select'],required=True)
    parser.add_argument('--workers',type=int,default=20)
    args=parser.parse_args()
    if not 1<=args.workers<=24:raise ValueError('one to24 workers')
    configure();record=protocol();cases=record['cases']
    if args.stage in ['folds','select']:
        if not read(RAW/'all_curve_families/audit_execution.json')['all_passed']:
            raise ValueError('audit all proposed final fits first')
        jobs,proposals=folds_setup(cases)
        if args.stage=='select':
            if not read(RAW/'family_predictive_guard/folds_execution.json')['all_passed']:
                raise ValueError('all confirmation folds must finish successfully')
            rows=[guard.select(c) if proposals[c] is not None else dict(case=c,adopted=False,
                  policy='published incumbent',reason='no paired-valid expanded proposal') for c in cases]
            write(RAW/'family_predictive_guard/selection.json',dict(rows=rows,all_passed=True,
                all20_cases_retained=True,selection_sealed_before_geographic_reporting=True))
            return
        function=guard.fold;out=RAW/'family_predictive_guard'
    else:
        jobs=[(c,args.stage) for c in cases];function=run_one;out=RAW
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(function,j) for j in jobs]):
            rows.append(future.result())
            write(out/(args.stage+'_progress.json'),dict(completed=len(rows),requested=len(jobs),rows=rows))
    write(out/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,
        all_passed=all(r['status']=='complete' for r in rows)))


if __name__=='__main__':main()
