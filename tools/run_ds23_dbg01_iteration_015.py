"""Next bounded worst-two batch using the unchanged ALGO02/03 reference."""

import csv
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

import run_ds23_dbg01_iteration_014 as previous
import repair_ds23_iteration009_targets as whole_track_guard
import repair_ds23_iteration010_bank as bank_guard
from run_ds23_dbg01_iteration_010 import stage_passed
from run_algo01_ds23_sample import ROOT,read,write,sha

engine=previous.engine
RAW=ROOT/'reports/2026_10_23_ds23_dbg01_iteration_015_raw'
CLOSED=previous.CLOSED+('DS23-0202','DS23-0262')
STAGES=previous.STAGES


def batch_cases(rows):return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;whole_track_guard.ORIGINAL_CONFIGURE()
    engine.reentry.nominate=whole_track_guard.guarded_nomination
    engine.dbg.engine.bank=bank_guard.bank_with_optional_archive


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=15,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],benchmark_sha256=sha(engine.baseline.BENCHMARK),
        source_sha256=sha(Path(__file__)),parent_report='reports/2026_10_23_ds23_dbg01_iteration_014/README.md',
        parent_published_commit='a9476f61cb80b91bffce38141e4f730519d09d4b',
        continue_original_ALGO02_ALGO03_engines=True,
        no014local_step_temporal_or_augmented_family_policy_adopted=True,
        paired_positive_guard_and_completed_deadline_policy_still_provisional_not_in_benchmark=True,
        prior0273paired_positive_guard_must_be_reused_as_existing_evidence_not_a_new_discovery=True,
        whole_track_and_rescued_scan_bank_guards_retained=True,
        cold_start=[0,0],regional_center=[37.906,-122.545],regional_width_km=25.,
        both_c_arms_same_observations_candidates_aliases_other_priors_gates_and_budgets=True,
        inference_no_GPS_following_TLE_manual_identities_or_stationary_pooling=True,
        no_new_RF_or_IQ_reprocessing=True,publish_every_bounded_iteration_including_negative=True,
        new_ALGO_release_requires_credible_matched_full_DS23_improvement=True,
        reuse_existing_case_and_grouped_or_singleton_evidence_before_repeating_prototypes=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration015 protocol')
    else:write(path,record)
    return record


def batch():
    record=protocol();path=RAW/'batch_execution.json'
    if path.exists():raise FileExistsError('preserve015 execution; explicit resume required')
    start=time.monotonic();progress=dict(cases=record['cases'],stages=[],all_terminal=False,running_stage=None,maximum_wall_seconds=1800,all_passed=False)
    for stage in STAGES:
        progress['running_stage']=stage;write(path,progress);tick=time.monotonic()
        with (RAW/(stage+'.log')).open('w') as stream:
            child=subprocess.Popen([sys.executable,'-B',str(Path(__file__)),'--stage',stage],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=child.wait(timeout=max(1,min(900,1800-(time.monotonic()-start))))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                code=124
        try:passed=code==0 and stage_passed(stage,RAW,record['cases'])
        except (FileNotFoundError,KeyError,ValueError):passed=False
        progress['stages'].append(dict(stage=stage,returncode=code,scientific_passed=passed,seconds=time.monotonic()-tick));print(stage,'complete' if passed else 'FAILED',flush=True)
        if not passed:break
    progress.update(all_terminal=True,running_stage=None,all_passed=len(progress['stages'])==len(STAGES) and all(r['scientific_passed'] for r in progress['stages']));write(path,progress)
    if not progress['all_passed']:raise SystemExit(1)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=STAGES);parser.add_argument('--batch',action='store_true');args=parser.parse_args()
    if args.batch:
        if args.stage:parser.error('choose batch or stage')
        batch();return
    if args.stage is None:parser.error('stage or batch required')
    engine.configure=configure;engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
