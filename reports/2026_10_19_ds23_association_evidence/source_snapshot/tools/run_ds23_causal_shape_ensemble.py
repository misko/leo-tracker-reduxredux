"""Two bounded workers: causal shape histories, external qualification, RF fits."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_causal_shape_ensemble import OUT,HISTORY
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    start=time.monotonic()
    with (OUT/(case+'.log')).open('w') as stream:
        commands=[['learn_ds23_causal_shape_forecast.py',str(HISTORY/(case+'.json'))],
            ['learn_ds23_causal_shape_ensemble.py',str(HISTORY/(case+'_shape_forecast.json'))],
            ['probe_ds23_causal_shape_ensemble.py','--case',case]]
        for command in commands:
            r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools'/command[0]),*command[1:]],
                cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                stdout=stream,stderr=stream,timeout=180)
            if r.returncode:raise RuntimeError(f'{case}: {command[0]} failed {r.returncode}')
    return dict(case=case,code=0,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,
        state_samples_s=[-150,0,150],forecast='phase-aligned previous/current ECEF state difference',
        selection='interpolate or extrapolate with pre-RF chronological qualification, else zero',
        strengths=[0,.125,.25,.5,.75,1],minimum_validation_transitions=30,
        RF_fallback='use original scalar-history result if either c arm fails a gate',
        fixed_current_primary_mask=True,no_trimming=True,no_GPS_selection=True,
        all_regional_candidates_calibrate_history=True,development_probes=['DS23-0217'],
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['learn_ds23_causal_shape_forecast.py',
            'learn_ds23_causal_shape_ensemble.py','probe_ds23_causal_shape_ensemble.py',
            'run_ds23_causal_shape_ensemble.py','probe_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
