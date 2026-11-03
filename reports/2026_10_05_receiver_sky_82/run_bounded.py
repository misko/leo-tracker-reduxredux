"""Checkpointed <=25 minute offline batches; never starts RF collection."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
PYTHON = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
STAGES = ('export','bank','refine','bootstrap','seed','calibrate','associate','pair')


def terminate(process):
    # Only this runner's exact private process group (including root workers).
    subprocess.run(['sudo','-n','kill','-TERM','--',f'-{process.pid}'], check=False, capture_output=True)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        subprocess.run(['sudo','-n','kill','-KILL','--',f'-{process.pid}'], check=False, capture_output=True)
        process.wait(timeout=8)


def one(label, stages, deadline, logs):
    results = []
    for stage in stages:
        if deadline-time.monotonic() < 30:
            results.append(dict(scan=label,stage=stage,status='batch_deadline_before_start'))
            break
        path = logs/f'{label}-{stage}.log'
        started = time.monotonic()
        with path.open('x') as stream:
            process = subprocess.Popen(['sudo','-n','nice','-n','10','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
                PYTHON,str(HERE/'process_stage.py'),stage,label],
                stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,
                env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1',
                     'MPLCONFIGDIR':str(logs/'mplconfig')})
            try:
                process.wait(timeout=min(600, deadline-started))
                status = 'complete' if process.returncode == 0 else 'failed'
            except subprocess.TimeoutExpired:
                terminate(process)
                status = 'bounded_timeout_checkpointed'
        row = dict(scan=label,stage=stage,status=status,returncode=process.returncode,
                   elapsed_s=time.monotonic()-started,log=str(path))
        results.append(row)
        (logs/f'{label}-progress.json').write_text(json.dumps(results,indent=2))
        print(json.dumps(row),flush=True)
        if status != 'complete':
            break
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels',nargs='+')
    p.add_argument('--stages',nargs='+',choices=STAGES,default=list(STAGES))
    p.add_argument('--workers',type=int,choices=(1,2),default=2)
    p.add_argument('--minutes',type=float,default=25)
    args = p.parse_args()
    if not 0 < args.minutes <= 25:
        raise ValueError('batch must be <=25 minutes')
    cohort = json.loads((HERE/'cohort.json').read_text())
    labels = args.labels or cohort['new_labels']
    if len(set(labels)) != len(labels) or not set(labels) <= set(cohort['new_labels']):
        raise ValueError('unknown or duplicate extension scan')
    logs = HERE/'batches'/str(time.time_ns())
    logs.mkdir(parents=True)
    deadline = time.monotonic()+args.minutes*60
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(one,label,args.stages,deadline,logs) for label in labels]):
            results.extend(future.result())
    (logs/'summary.json').write_text(json.dumps(results,indent=2))
    print('BATCH_SAVED',str(logs),flush=True)


if __name__ == '__main__':
    main()
