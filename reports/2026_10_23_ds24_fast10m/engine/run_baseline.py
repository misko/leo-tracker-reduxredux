"""Bounded fresh-input baseline supervisor; each case is process isolated."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import signal
import time

REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OUT=Path(__file__).resolve().parents[1]
PYTHON=REPO/'.venv/bin/python'
ENV=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
         MKL_NUM_THREADS='1',PYTHONPATH='/tmp/algo03-feasible-deps:'+str(OUT/'engine')+':src:tools')


def run_command(cmd,log,cap):
    """Kill the isolated job's descendants as well as its supervisor at cap."""
    with subprocess.Popen(cmd,cwd=REPO,env=ENV,stdout=log,stderr=subprocess.STDOUT,
                          start_new_session=True) as child:
        try:
            return child.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            try: os.killpg(child.pid,signal.SIGKILL)
            except (ProcessLookupError,PermissionError): pass
            # Preparation may have elevated read-only descendants. Restrict
            # the elevated signal to this newly created job's process group.
            subprocess.run(['sudo','-n','kill','-KILL','--','-'+str(child.pid)],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            child.wait()
            raise


def one(case):
    folder=OUT/case; folder.mkdir(exist_ok=True)
    stages=[('export',['sudo','-n','env',*[f'{k}={ENV[k]}' for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')],str(PYTHON),'tools/prepare_algo02_ds23.py','--run-dir',str(OUT),'--case',case,'--stage','export'],180),
            ('prepare',['sudo','-n','env',*[f'{k}={ENV[k]}' for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')],str(PYTHON),'tools/prepare_algo02_ds23.py','--run-dir',str(OUT),'--case',case,'--stage','prepare'],600),
            ('algo02',[str(PYTHON),'tools/algo02_scan.py','--run-dir',str(OUT),'--case',case,'--stage','all'],900),
            ('cavity',[str(PYTHON),str(OUT/'engine/ds24_engine.py'),'--root',str(OUT),'--case',case],960)]
    receipt=dict(case=case,stages=[],status='running'); began=time.monotonic()
    try:
        for name,cmd,cap in stages:
            mark=time.monotonic()
            with (folder/(name+'.log')).open('a') as log:
                returncode=run_command(cmd,log,cap)
            receipt['stages'].append(dict(stage=name,returncode=returncode,seconds=time.monotonic()-mark))
            if returncode: raise RuntimeError(name+' exited '+str(returncode))
            if name=='prepare':
                prepared=json.loads((folder/'prepared.json').read_text())
                if prepared['status']!='prepared':
                    receipt.update(status='input_unqualified',reason=prepared['status']);return receipt
            if name=='algo02':
                baseline=json.loads((folder/'algo02_result.json').read_text())
                if baseline['status']!='accepted':
                    receipt.update(status='reference_unqualified',reason=baseline.get('reason'));return receipt
            if name=='cavity':
                reference=OUT/'family_cavity/position'/(case+'.json')
                if not reference.exists():
                    receipt.update(status='reference_failed',reason='family cavity position unavailable');return receipt
                reference_result=json.loads(reference.read_text())
                if reference_result['status']!='complete':
                    receipt.update(status='reference_failed',reason=reference_result.get('error'));return receipt
        receipt['status']='complete'
    except Exception as exc: receipt.update(status='execution_failed',error=repr(exc))
    finally:
        receipt['seconds']=time.monotonic()-began
        (folder/'baseline_execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cases',nargs='+');p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    if not 1<=a.workers<=4: p.error('workers must be 1..4')
    members=json.loads((OUT/'sample.json').read_text())['selected'];allowed={m['dataset_label'] for m in members}
    cases=a.cases or sorted(allowed)
    if not set(cases)<=allowed:p.error('case outside sealed DS24 cohort')
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for f in as_completed([pool.submit(one,c) for c in cases]):print(json.dumps(f.result()),flush=True)
