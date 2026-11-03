"""At most 25 minutes of low-priority, two-scan offline work per invocation."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
PYTHON='/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
STAGES=('export','bank','refine','bootstrap','calibrate','associate','position')


def terminate(process):
    subprocess.run(['sudo','-n','kill','-TERM','--',f'-{process.pid}'],check=False,capture_output=True)
    try:process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        subprocess.run(['sudo','-n','kill','-KILL','--',f'-{process.pid}'],check=False,capture_output=True)
        process.wait(timeout=8)


def one(label,stages,deadline,logs,refinement_workers):
    records=[]
    for stage in stages:
        remaining=deadline-time.monotonic()
        if remaining<30:break
        path=logs/f'{label}-{stage}.log'
        begun=time.monotonic()
        with path.open('x') as stream:
            process=subprocess.Popen(['sudo','-n','nice','-n','15','env','OPENBLAS_NUM_THREADS=1',
                'OMP_NUM_THREADS=1','NUMBA_NUM_THREADS=1',f'MPLCONFIGDIR={logs}/mplconfig',
                f'RECENT_V16_REFINEMENT_WORKERS={refinement_workers}',
                PYTHON,str(HERE/'process_stage.py'),stage,label],
                stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                process.wait(timeout=remaining if stage=='refine' else min(600.,remaining))
                status=('complete' if process.returncode==0 else
                        'interrupted_checkpointed' if process.returncode<0 else 'failed_or_input_pending')
            except subprocess.TimeoutExpired:
                terminate(process)
                status='bounded_timeout_checkpointed'
        row=dict(scan=label,stage=stage,status=status,returncode=process.returncode,
                 elapsed_s=time.monotonic()-begun,log=str(path))
        records.append(row)
        (logs/f'{label}-progress.json').write_text(json.dumps(records,indent=2))
        print(json.dumps(row),flush=True)
        if status!='complete':break
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels',nargs='+')
    p.add_argument('--stages',nargs='+',choices=STAGES,default=list(STAGES))
    p.add_argument('--minutes',type=float,default=25.)
    p.add_argument('--workers',type=int,choices=(1,2),default=2)
    p.add_argument('--refinement-workers',type=int,choices=(1,2,4),default=2)
    a=p.parse_args()
    if not 0<a.minutes<=25:raise ValueError('Maximum invocation 25 minutes')
    if a.workers*a.refinement_workers>4:raise ValueError('At most four concurrent refinement workers')
    cohort=json.loads((HERE/'cohort-final.json').read_text())
    scans=cohort['scans']
    # Alternate rates; readiness does not change which captures are selected.
    order=sorted(scans,key=lambda r:(r['label'][-2:],r['sample_rate_hz']))
    labels=a.labels or [r['label'] for r in order]
    if len(set(labels))!=len(labels) or not set(labels)<={r['label'] for r in scans}:
        raise ValueError('Unknown or duplicate cohort labels')
    logs=HERE/'batches'/str(time.time_ns())
    logs.mkdir(parents=True)
    deadline=time.monotonic()+60*a.minutes
    output=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(one,label,a.stages,deadline,logs,a.refinement_workers) for label in labels]
        for future in as_completed(futures):
            output.extend(future.result())
            subprocess.run([sys.executable,str(HERE/'summarize.py')],check=True)
    (logs/'summary.json').write_text(json.dumps(output,indent=2))
    print('BATCH_SAVED',str(logs),flush=True)
