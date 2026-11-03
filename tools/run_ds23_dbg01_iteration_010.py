"""Bounded next-two DBG01 batch with whole-track and scientific-receipt guards."""

import csv
from pathlib import Path
import subprocess
import sys
import time
import os
import signal

import repair_ds23_iteration009_targets as previous
from run_algo01_ds23_sample import ROOT,read,sha,write

engine=previous.engine
RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_010_raw'
CLOSED=previous.runner.CLOSED+('DS23-0028','DS23-0311')
STAGES=('inventory','screen','nominations','positions','reentry_audit','support','support_finalize',
        'dbg_prepare','dbg_audit_discover','dbg_bank','dbg_analysis','independent_audit','restart_selection')


def batch_cases(rows):return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;previous.ORIGINAL_CONFIGURE()
    engine.reentry.nominate=previous.guarded_nomination


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=10,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),source_sha256=sha(Path(__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_009/README.md',
        parent_published_commit='8788bcc3306aa0f09ffadcb67df9db2020ec06c1',
        continue_original_ALGO02_ALGO03_engines=True,iteration009_covariance_and_partial_trials_not_adopted=True,
        whole_nomination_input_guard_sha256=sha(Path(previous.__file__)),
        partial_original_GLRT_preserved_in_inventory=True,
        scientific_worker_receipts_checked_before_dependent_stages=True,
        regional_center=[37.906,-122.545],regional_width_km=25.,cold_fit_start=[0.,0.],
        both_c_arms_same_observations_candidates_other_priors_gates_and_budgets=True,
        inference_no_GPS_following_TLE_manual_identities_or_stationary_pooling=True,
        no_new_RF_or_IQ_reprocessing=True,publish_all_bounded_iteration_results=True,
        no_ALGO_release_without_matched_full_DS23_confirmation=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration010 protocol')
    else:write(path,record)
    return record


def stage_passed(stage,root,cases):
    receipts=dict(inventory='inventory_execution.json',screen='screen_execution.json',
        nominations='single_curve_reentry/nominations_execution.json',positions='single_curve_reentry/positions_execution.json',
        reentry_audit='single_curve_reentry/audit_execution.json',support='support_aware_reentry/execution.json',
        support_finalize='support_aware_reentry/finalization_audit.json',
        dbg_audit_discover='DBG01_audit_discover_execution.json',dbg_analysis='DBG01_analysis_execution.json',
        independent_audit='independent_iteration_audit.json')
    if stage in receipts:
        data=read(root/receipts[stage]);return bool(data.get('all_passed') and data.get('all_terminal',True))
    if stage=='dbg_prepare':return all((root/c/'DBG01/protocol.json').exists() for c in cases)
    if stage=='dbg_bank':return all(bool(read(root/c/'DBG01/hypothesis_bank.json')['nodes']) for c in cases)
    if stage=='restart_selection':
        data=read(root/'RF_restart_selection.json')
        return bool(data['selection_frozen_before_new_geographic_error_comparison'] and {r['case'] for r in data['rows']}==set(cases))
    raise ValueError('unknown scientific stage')


def batch():
    record=protocol();path=RAW/'batch_execution.json'
    if path.exists():raise FileExistsError('preserve batch execution; explicit resume required')
    start=time.monotonic();progress=dict(cases=record['cases'],stages=[],all_terminal=False,running_stage=None,
        maximum_wall_seconds=1800,all_passed=False)
    for stage in STAGES:
        progress['running_stage']=stage;write(path,progress);tick=time.monotonic()
        with (RAW/(stage+'.log')).open('w') as stream:
            child=subprocess.Popen([sys.executable,'-B',str(Path(__file__)),'--stage',stage],cwd=ROOT,
                stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=child.wait(timeout=max(1,min(900,1800-(time.monotonic()-start))))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                code=124
        try:passed=code==0 and stage_passed(stage,RAW,record['cases'])
        except (FileNotFoundError,KeyError,ValueError):passed=False
        progress['stages'].append(dict(stage=stage,returncode=code,scientific_passed=passed,seconds=time.monotonic()-tick))
        print(stage,'complete' if passed else 'FAILED',flush=True)
        if not passed:break
    progress.update(all_terminal=True,running_stage=None,all_passed=all(r['scientific_passed'] for r in progress['stages']) and len(progress['stages'])==len(STAGES))
    write(path,progress)
    if not progress['all_passed']:raise SystemExit(1)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=STAGES);parser.add_argument('--batch',action='store_true');args=parser.parse_args()
    if args.batch:
        if args.stage:parser.error('choose batch or single stage')
        batch();return
    if args.stage is None:parser.error('stage or batch required')
    engine.configure=configure;engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
