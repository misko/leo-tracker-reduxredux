"""Two bounded workers for the declared variance-matched band covariance study."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_band_covariance import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    start=time.monotonic();path=OUT/(case+'.json')
    if path.exists() and read(path)['source_sha256']==sha(ROOT/'tools/probe_ds23_band_covariance.py'):
        assert set(read(path)['results'])=={'1.0','0.5','0.0'}
        return dict(case=case,code=0,seconds=0.,reused_completed_probe=True)
    with (OUT/(case+'.log')).open('w') as stream:
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/probe_ds23_band_covariance.py'),'--case',case],
            cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=stream,stderr=stream,timeout=240)
    return dict(case=case,code=r.returncode,seconds=time.monotonic()-start,reused_completed_probe=False)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,cross_band_correlations=[1.,.5,0.],
        control='1.0 reproduces scalar history prior with receiver support',
        development_probes=['DS23-0217','DS23-0202'],GPS_selection=False,
        within_band_covariance_and_marginal_smooth_variance_preserved=True,
        all_cases_run_including_low_only_null_controls=True,initial_data_labels_aliases_noise_and_c_pair_budgets_matched=True,
        budgets=dict(phase_rounds=5,position_steps=48,paired_gate_rounds=4,case_timeout_s=240),
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_band_covariance.py','run_ds23_band_covariance.py','probe_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
