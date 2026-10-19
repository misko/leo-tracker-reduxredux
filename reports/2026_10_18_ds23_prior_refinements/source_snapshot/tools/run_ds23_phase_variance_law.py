"""Bounded two-worker test of causal predictive variance-law selection."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed

from probe_ds23_history_calibrated_phase import HISTORY
from probe_ds23_phase_variance_law import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    start=time.monotonic()
    env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with (OUT/(case+'.log')).open('w') as stream:
        commands=[['learn_ds23_phase_variance_law.py',str(HISTORY/(case+'_forecast.json'))],
                  ['probe_ds23_phase_variance_law.py','--case',case]]
        for command in commands:
            r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools'/command[0]),*command[1:]],
                cwd=ROOT,env=env,stdout=stream,stderr=stream,timeout=240)
            if r.returncode:raise RuntimeError(f'{case} {command[0]} failed: {r.returncode}')
    return dict(case=case,code=0,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,primary='variance_law_and_mean if earlier-TLE validation qualifies, else scalar',
        validation_is_strictly_pre_RF=True,GPS_selection=False,other_priors_masks_budgets_match_scalar_cohort=True,
        law='clip(hypot(floor_s, gain * old_new_alignment_s * age_s / epoch_gap_s), .02, 15)',
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['learn_ds23_phase_variance_law.py','probe_ds23_phase_variance_law.py','run_ds23_phase_variance_law.py',
            'probe_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
