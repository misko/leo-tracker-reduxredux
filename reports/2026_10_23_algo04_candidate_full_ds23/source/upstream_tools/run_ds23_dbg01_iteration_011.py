"""Next bounded DBG01 cases; rejected010 experimental rules remain disabled."""

import csv
from pathlib import Path
import subprocess
import sys
import time
import os
import signal

import run_ds23_dbg01_iteration_010 as previous
import repair_ds23_iteration010_bank as bank_repair
from run_algo01_ds23_sample import ROOT,read,write,sha

engine=previous.engine
RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_011_raw'
CLOSED=previous.CLOSED+('DS23-0080','DS23-0257')
STAGES=previous.STAGES


def batch_cases(rows):return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;previous.previous.ORIGINAL_CONFIGURE()
    engine.reentry.nominate=previous.previous.guarded_nomination
    engine.dbg.engine.bank=bank_repair.bank_with_optional_archive


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=11,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),source_sha256=sha(Path(__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_010/README.md',
        parent_published_commit='e86ec48fbd6984d927ab5f61e37fb2434b41077a',
        continue_existing_ALGO02_ALGO03_engines=True,no_010_short_curvature_or_temporal_policy_adopted=True,
        whole_track_guard_sha256=sha(Path(previous.previous.__file__)),rescued_scan_bank_guard_sha256=sha(Path(bank_repair.__file__)),
        saved0209short_confirmation_result='reports/2026_10_22_ds23_dbg01_iteration_010_raw/short_confirmation20_v2/short_whole_curves/DS23-0209.json',
        reuse0209short_curve_evidence_do_not_repeat_same_prototype=True,
        cold_start=[0,0],regional_center=[37.906,-122.545],regional_width_km=25.,
        both_c_arms_same_observations_candidates_aliases_other_priors_gates_and_budgets=True,
        inference_no_GPS_following_TLE_manual_identities_or_stationary_pooling=True,
        no_new_RF_or_IQ_reprocessing=True,publish_every_bounded_iteration=True,
        new_ALGO_release_requires_credible_matched_full_DS23_accuracy_improvement=True,
        next_family_adequacy_hypothesis_requires_review_of_existing_outlier_and_cavity_work_before_implementation=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration011 protocol')
    else:write(path,record)
    return record


def batch():
    record=protocol();path=RAW/'batch_execution.json'
    if path.exists():raise FileExistsError('preserve011 execution; explicit resume required')
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
        try:passed=code==0 and previous.stage_passed(stage,RAW,record['cases'])
        except (FileNotFoundError,KeyError,ValueError):passed=False
        progress['stages'].append(dict(stage=stage,returncode=code,scientific_passed=passed,seconds=time.monotonic()-tick))
        print(stage,'complete' if passed else 'FAILED',flush=True)
        if not passed:break
    progress.update(all_terminal=True,running_stage=None,all_passed=len(progress['stages'])==len(STAGES) and all(r['scientific_passed'] for r in progress['stages']))
    write(path,progress)
    if not progress['all_passed']:raise SystemExit(1)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=STAGES);parser.add_argument('--batch',action='store_true');args=parser.parse_args()
    if args.batch:
        if args.stage:parser.error('choose batch or single stage')
        batch();return
    if args.stage is None:parser.error('stage or batch required')
    engine.configure=configure;engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
