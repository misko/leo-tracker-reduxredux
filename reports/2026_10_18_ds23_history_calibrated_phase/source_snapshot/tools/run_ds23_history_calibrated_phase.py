"""Two bounded workers: read causal histories, calibrate priors, fit positions."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed

from probe_ds23_history_calibrated_phase import OUT,HISTORY
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,read,sha,write


def worker(case):
    start=time.monotonic()
    env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    history=HISTORY/(case+'.json');log=OUT/(case+'.log')
    with log.open('a') as stream:
        if not history.exists():
            temporary=history.with_suffix('.tmp')
            with temporary.open('w') as target:
                r=subprocess.run(['sudo','-n','env','PYTHONPATH=src:tools','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
                    str(ROOT/'.venv/bin/python'),str(ROOT/'tools/export_ds23_causal_history.py'),'--case',case],
                    cwd=ROOT,env=env,stdout=target,stderr=stream,timeout=180)
            if r.returncode:raise RuntimeError(f'causal history export failed: {case}')
            assert read(temporary)['case']==case
            temporary.replace(history)
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/learn_ds23_causal_phase_forecast.py'),str(history)],
                          cwd=ROOT,env=env,stdout=stream,stderr=stream,timeout=120)
        if r.returncode:raise RuntimeError(f'causal forecast calibration failed: {case}')
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/probe_ds23_history_calibrated_phase.py'),'--case',case],
                          cwd=ROOT,env=env,stdout=stream,stderr=stream,timeout=240)
        if r.returncode:raise RuntimeError(f'calibrated position fit failed: {case}')
    return dict(case=case,code=r.returncode,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True);HISTORY.mkdir(parents=True,exist_ok=True)
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,prior_calibration_uses_only_pre_RF_TLE_history=True,
        candidate_history_is_not_RF_family_whitelist=True,history_window_hours=72,
        historical_temporal_split=.7,hyperparameters=dict(shrinkage=[0,.25,.5,.75,1],
            prior_nu=[None,3,4,8,16],sigma_multiplier_range=[.1,4]),
        qualification='heldout earlier-TLE predictive density improves, ≥30 transitions; else Gaussian zero-mean baseline',
        primary_algorithm='mean_and_distribution',ablations=['baseline','mean_only','distribution_only'],
        GPS_used_for_selection_or_fitting=False,c0_fitted_c_matched=True,
        regional_center=[37.906,-122.545],box_width_km=25,position_start=[0,0],
        budgets=dict(phase_rounds=5,steps_per_round=48,paired_gate_rounds=4),
        original_sample_sha256=sha(SOURCE/'sample.json'),
        code_sha256={name:sha(ROOT/'tools'/name) for name in ['export_ds23_causal_history.py',
            'learn_ds23_causal_phase_forecast.py','probe_ds23_history_calibrated_phase.py',
            'run_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],status='failed',reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts)
            print(r,flush=True)


if __name__=='__main__':run()
