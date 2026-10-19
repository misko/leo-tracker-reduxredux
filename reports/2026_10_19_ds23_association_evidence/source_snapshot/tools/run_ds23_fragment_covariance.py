"""Bounded fixed-data fragment-covariance comparison across the 20-scan sample."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_fragment_covariance import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    path=OUT/(case+'.json');start=time.monotonic()
    if path.exists() and read(path)['source_sha256']==sha(ROOT/'tools/probe_ds23_fragment_covariance.py'):
        return dict(case=case,code=0,reused_completed_probe=True,seconds=0.)
    with (OUT/(case+'.log')).open('w') as stream:
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/probe_ds23_fragment_covariance.py'),'--case',case],
            cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=stream,stderr=stream,timeout=240)
    return dict(case=case,code=r.returncode,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,correlations=[0.,.5,.9],
        prior='same satellite and exact recorded RF; each fragment marginal offset sigma300Hz',
        primary='minimum c0 normalized generalized RF loss among covariance choices passing both c arms',
        fixed_rho_policy='fallback to rho0 if either c arm fails a gate',
        fixed_current_primary_mask=True,no_trimming=True,no_GPS_selection=True,
        development_probes=['DS23-0217','DS23-0257'],
        budgets=dict(phase_rounds=5,position_steps=48,case_timeout_s=240),
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_fragment_covariance.py','run_ds23_fragment_covariance.py','probe_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
