"""Two bounded workers for causal per-satellite phase-scale adaptation."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_history_calibrated_phase import HISTORY
from probe_ds23_satellite_phase_scale import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    start=time.monotonic()
    with (OUT/(case+'.log')).open('w') as stream:
        commands=[['learn_ds23_satellite_phase_scale.py',str(HISTORY/(case+'_forecast.json'))],
                  ['probe_ds23_satellite_phase_scale.py','--case',case]]
        for command in commands:
            result=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools'/command[0]),*command[1:]],
                cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                stdout=stream,stderr=stream,timeout=180)
            if result.returncode:raise RuntimeError(f'{case}: {command[0]} failed {result.returncode}')
    return dict(case=case,code=0,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,prior='variance-one population-centered log-scale mixture; moment-matched predictive Student',
        scale_spreads=[0.,.25,.5,1.],historical_split=.7,minimum_validation_rows=30,
        required_predictive_gain='log(validation transition count)',qualification_uses_pre_RF_TLE_only=True,
        candidate_bank_wide_not_RF_family_whitelist=True,GPS_selection=False,
        original_initial_data_labels_aliases_priors_and_c_pair_budgets_matched=True,
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['learn_ds23_satellite_phase_scale.py','probe_ds23_satellite_phase_scale.py',
            'run_ds23_satellite_phase_scale.py','probe_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
