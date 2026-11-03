"""Full available DS23 assessment of the frozen grouped predictive experiment."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import run_ds23_dbg01_iteration_007 as runner
import confirm_ds23_new_family_prediction as engine
from run_algo01_ds23_sample import read,write,sha

PARENT=runner.RAW
OUT=PARENT/'new_family_full_DS23'
COHORT=engine.OUT


def preserve_link(destination,source):
    if destination.exists():
        if sha(destination)!=sha(source):raise ValueError('reuse target differs from frozen source')
    else:destination.symlink_to(source.resolve())


def prepare():
    OUT.mkdir(exist_ok=True);(OUT/'linear_family_groups').mkdir(exist_ok=True)
    source=read(COHORT/'protocol.json');authority=read(engine.AUTHORITY)
    for name,expected in source['source_sha256'].items():
        if sha(Path(__file__).with_name(name))!=expected:raise ValueError('random20 inference source changed')
    cases=sorted(r['case'] for r in authority['case_result_sha256']);assert len(cases)==410
    record=dict(cases=cases,dataset_total=413,unavailable=['DS23-0012','DS23-0184','DS23-0286'],
        workers=30,source_sha256=sha(Path(__file__)),frozen_inference_source_sha256=source['source_sha256'],
        random20_protocol_sha256=sha(COHORT/'protocol.json'),same_rules_for_all_cases=True,
        all20_random_cases_and_both_development_cases_reused_without_refitting=True,
        primary='physical_prior',ablation='phase_only',paired_c0_fitted_c=True,
        exact_incumbent_fallback_for_no_proposal_failed_gate_or_failed_job=True,
        no_GPS_or_following_TLE_or_new_RF_or_extra_point_trimming=True,
        no_endpoint_quarantine_extension_in_this_frozen_full_method=True,
        full_population_same_site_not_new_location_validation=True)
    if (OUT/'protocol.json').exists():
        if read(OUT/'protocol.json')!=record:raise ValueError('preserve full assessment protocol')
    else:write(OUT/'protocol.json',record)
    receipts=[]
    for case in source['cases']:
        folder=OUT/case;folder.mkdir(exist_ok=True)
        for name in ['inventory.json','selection.json','result.json']:preserve_link(folder/name,COHORT/case/name)
        preserve_link(OUT/'linear_family_groups'/(case+'.json'),COHORT/'linear_family_groups'/(case+'.json'))
        receipts.append(dict(case=case,status=read(folder/'result.json')['status'],reused=True,
            source_result_sha256=sha(COHORT/case/'result.json')))
    for case in ['DS23-0227','DS23-0400']:
        folder=OUT/case;folder.mkdir(exist_ok=True)
        preserve_link(folder/'inventory.json',PARENT/case/'inventory.json')
        preserve_link(folder/'selection.json',PARENT/'new_family_prediction_v2'/(case+'_selection.json'))
        preserve_link(OUT/'linear_family_groups'/(case+'.json'),PARENT/'linear_family_groups'/(case+'.json'))
        prior=PARENT/'new_family_prediction_v2'/(case+'.json');saved=read(prior)
        write(folder/'result.json',dict(saved,status='complete',entries=read(folder/'selection.json')['entries'],
            source_result_sha256=sha(prior),development_reused_without_refitting=True))
        receipts.append(dict(case=case,status='complete',reused=True,source_result_sha256=sha(prior)))
    write(OUT/'reuse_receipts.json',dict(rows=receipts,all_regressions_also_reused=True))
    return cases,receipts


def one(case):
    engine.OUT=OUT
    try:return engine.one(case)
    except Exception as exc:return dict(case=case,status='failed',error=repr(exc),exact_incumbent_fallback=True)


def main():
    cases,rows=prepare();completed={r['case'] for r in rows};began=time.monotonic()
    with ProcessPoolExecutor(max_workers=30) as pool:
        for future in as_completed([pool.submit(one,c) for c in cases if c not in completed]):
            r=future.result();rows.append(r);print(r,flush=True)
            write(OUT/'progress.json',dict(rows=rows,completed=len(rows),total=len(cases),seconds=time.monotonic()-began))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,cases=len(cases),seconds=time.monotonic()-began,
        RF_selection_complete_before_full_geographic_scoring=True,all_failed_jobs_remain_in_evaluation_as_incumbent_fallbacks=True))


if __name__=='__main__':main()
