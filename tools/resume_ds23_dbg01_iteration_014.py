"""Resume014 after orchestration SIGTERM; retain the completed scientific stages."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import run_ds23_dbg01_iteration_014 as study
from run_algo01_ds23_sample import ROOT,read,write,sha


def recovered_progress(progress):
    if progress['all_terminal']:raise ValueError('do not resume a terminal batch')
    done=[r['stage'] for r in progress['stages']]
    if done!=list(study.STAGES[:len(done)]) or not all(r['scientific_passed'] for r in progress['stages']):raise ValueError('completed stages must form a passing prefix')
    pending=progress['running_stage']
    if pending!=study.STAGES[len(done)]:raise ValueError('pending stage does not follow completed prefix')
    if not study.stage_passed(pending,study.RAW,progress['cases']):raise ValueError('orphaned stage must finish its scientific receipt before resume')
    return dict(progress,stages=progress['stages']+[dict(stage=pending,returncode=None,scientific_passed=True,
        recovered_from_terminal_scientific_receipt_after_orchestrator_SIGTERM=True)],running_stage=None)


def main():
    study.protocol();path=study.RAW/'batch_execution.json';original=read(path)
    if (study.RAW/'orchestration_resume.json').exists():raise FileExistsError('preserve explicit resume receipt')
    progress=recovered_progress(original);remaining=1800-(time.time()-(study.RAW/'protocol.json').stat().st_mtime)
    if remaining<=0:raise TimeoutError('original total1800second wall budget expired')
    write(study.RAW/'orchestration_resume.json',dict(original_progress=original,source_sha256=sha(Path(__file__)),
        parent_orchestrator_exit_code=143,positions_scientific_receipt_passes=True,no_refit_of_completed_stages=True,
        remaining_original_wall_seconds=remaining))
    write(path,progress);start=time.monotonic()
    for stage in study.STAGES[len(progress['stages']):]:
        progress['running_stage']=stage;write(path,progress);tick=time.monotonic()
        with (study.RAW/(stage+'.log')).open('w') as stream:
            child=subprocess.Popen([sys.executable,'-B',str(ROOT/'tools/run_ds23_dbg01_iteration_014.py'),'--stage',stage],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:code=child.wait(timeout=max(1,min(900,remaining-(time.monotonic()-start))))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                code=124
        try:passed=code==0 and study.stage_passed(stage,study.RAW,progress['cases'])
        except (FileNotFoundError,KeyError,ValueError):passed=False
        progress['stages'].append(dict(stage=stage,returncode=code,scientific_passed=passed,seconds=time.monotonic()-tick));print(stage,'complete' if passed else 'FAILED',flush=True)
        if not passed:break
    progress.update(all_terminal=True,running_stage=None,all_passed=len(progress['stages'])==len(study.STAGES) and all(r['scientific_passed'] for r in progress['stages']));write(path,progress)
    if not progress['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
