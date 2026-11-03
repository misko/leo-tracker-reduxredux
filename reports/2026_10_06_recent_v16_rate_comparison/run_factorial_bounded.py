"""At most 25 minutes, two low-priority factorial workers; no IQ refinement here.

Run original calibration/discovery once per scan; refined inputs must already
be complete. Timeout/failed/pending cases remain visible, never zero error.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
import subprocess
import sys
import time
import factorial as study
from run_bounded import PYTHON,terminate


def planned_jobs(label,refinements=('original','refined')):
    if not refinements or not set(refinements)<=set(study.REFINEMENTS):
        raise ValueError('Unknown or empty refinement selection')
    jobs=[('original',['original','--label',label])] if 'original' in refinements else []
    for refinement,model,cone in study.cases():
        if refinement not in refinements:continue
        jobs.append((f'{refinement}-{model}-{cone}', ['position','--label',label,
            '--refinement',refinement,'--model',model,'--cone',cone]))
    return jobs


def one(label,deadline,logs,refinements=('original','refined')):
    records=[]
    for name,args in planned_jobs(label,refinements):
        remaining=deadline-time.monotonic()
        if remaining<30: break
        begun=time.monotonic();path=logs/f'{label}-{name}.log'
        with path.open('x') as stream:
            proc=subprocess.Popen(['sudo','-n','nice','-n','15','env','OPENBLAS_NUM_THREADS=1',
                'OMP_NUM_THREADS=1','NUMBA_NUM_THREADS=1',f'MPLCONFIGDIR={logs}/mplconfig',
                PYTHON,str(study.stage.HERE/'factorial.py'),*args],stdout=stream,stderr=subprocess.STDOUT,
                start_new_session=True)
            try:
                proc.wait(timeout=min(600. if name=='original' else 240.,remaining))
                status='complete' if proc.returncode==0 else 'failed_or_input_pending'
            except subprocess.TimeoutExpired:
                terminate(proc);status='bounded_timeout'
        row=dict(scan=label,case=name,status=status,returncode=proc.returncode,
                 elapsed_s=time.monotonic()-begun,log=str(path))
        records.append(row)
        (logs/f'{label}-progress.json').write_text(json.dumps(records,indent=2))
        print(json.dumps(row),flush=True)
        subprocess.run([sys.executable,str(study.stage.HERE/'summarize_factorial.py')],check=True)
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels',nargs='+',required=True)
    p.add_argument('--minutes',type=float,default=25.)
    p.add_argument('--workers',type=int,choices=(1,2),default=2)
    p.add_argument('--refinements',nargs='+',choices=study.REFINEMENTS,default=list(study.REFINEMENTS))
    a=p.parse_args()
    if not 0<a.minutes<=25: raise ValueError('Maximum invocation 25 minutes')
    cohort=json.loads(study.stage.COHORT.read_text())['scans']
    if len(set(a.labels))!=len(a.labels) or not set(a.labels)<={r['label'] for r in cohort}:raise ValueError('Unknown/duplicate labels')
    study.freeze();logs=study.REPORT/'batches'/str(time.time_ns());logs.mkdir(parents=True)
    deadline=time.monotonic()+60*a.minutes
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        tasks=[pool.submit(one,label,deadline,logs,a.refinements) for label in a.labels]
        results=[r for f in as_completed(tasks) for r in f.result()]
    (logs/'summary.json').write_text(json.dumps(results,indent=2))
