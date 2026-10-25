"""Bounded DBG01 on0221/0322; preserve and re-audit0322's completed trials."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from pathlib import Path
import shutil
import sys

import run_ds23_dbg01_iteration_002 as engine
from run_algo01_ds23_sample import ROOT, read, sha, write

RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_004_raw'
PRIOR=ROOT/'reports/2026_10_22_ds23_curve_guard_confirmation_raw'
CLOSED=('DS23-0081','DS23-0326','DS23-0035','DS23-0041','DS23-0111','DS23-0390','DS23-0405')


def batch_cases(rows):
    return engine.next_cases(rows,closed=CLOSED)


def reusable_inventory(old,new):
    return all(old[a]['accepted_observation_ids']==new[a]['accepted_observation_ids']
               and old[a]['active_curved_points']==new[a]['active_curved_points']
               and old[a]['predictive_points']==new[a]['predictive_points']
               and old[a]['endpoint']==new[a]['endpoint'] for a in ['c0','fitted_c'])


def configure():
    engine.RAW=RAW;engine.configure()


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=4,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),
        source_sha256=sha(Path(__file__)),engine_sha256=sha(Path(engine.__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_003/README.md',
        parent_published_commit='92aa18b979371ad0c3dcf08b49c10410a8c19ea1',
        reuse0322_confirmation_nomination_and_position_trials=True,
        reuse_requires_identical_original_inventory_IDs_masks_counts_and_RF_endpoints=True,
        copied_trials_get_fresh_independent_endpoint_audit=True,
        regional_center=[37.906,-122.545],regional_width_km=25.,
        all_active_families_and_curved_tracks_ablated=True,
        both_c_arms_same_observations_candidates_other_priors_and_budgets=True,
        inference_no_GPS_following_TLE_manual_identities_or_stationary_pooling=True,
        no_new_RF_or_IQ_reprocessing=True,
        no_guard_tuning_on_previous_confirmation_GPS=True,
        publish_all_bounded_iteration_results=True,no_ALGO_release_without_full_DS23_confirmation=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration004 protocol')
    else:write(path,record)
    return record


def reuse(case,stage):
    old=read(PRIOR/case/'inventory.json')['arms'];new=read(RAW/case/'inventory.json')['arms']
    if not reusable_inventory(old,new):raise ValueError('0322 current context differs; do not reuse a stale trial')
    source=PRIOR/'single_curve_reentry'/(case+'_'+stage+'.json')
    dest=RAW/'single_curve_reentry'/source.name
    if dest.exists():raise FileExistsError('preserve copied research evidence')
    shutil.copyfile(source,dest)
    record=dict(case=case,stage=stage,status='complete',reused=True,source=str(source),
        source_sha256=sha(source),copied_sha256=sha(dest),matching_original_inventory_verified=True)
    write(dest.with_name(dest.stem+'_reuse_receipt.json'),record)
    return record


def main():
    configure();record=protocol()
    if '--stage' not in sys.argv:raise ValueError('explicit stage required')
    stage=sys.argv[sys.argv.index('--stage')+1]
    if stage in ['nominations','positions','reentry_audit']:
        folder=RAW/'single_curve_reentry';folder.mkdir(exist_ok=True)
        sub=dict(cases=record['cases'],source_sha256=sha(Path(engine.reentry.__file__)),
            protocol_sha256=sha(RAW/'protocol.json'),reuse0322_from=str(PRIOR),
            original_nomination_fit_and_audit_functions_unchanged=True)
        p=folder/'protocol.json'
        if p.exists():
            if read(p)!=sub:raise ValueError('preserve frozen reentry protocol')
        else:write(p,sub)
        actual='audit' if stage=='reentry_audit' else stage
        if stage=='reentry_audit':
            with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(engine.reentry.one,record['cases'],[actual]*2))
        else:
            rows=[reuse('DS23-0322',actual),engine.reentry.one('DS23-0221',actual)]
        write(folder/(actual+'_execution.json'),dict(rows=rows,all_terminal=True,
            all_passed=all(r['status']=='complete' for r in rows)))
    else:
        engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
