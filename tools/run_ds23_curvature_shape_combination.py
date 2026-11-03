"""Two bounded workers for the frozen curvature/shape composition."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_curvature_shape_combination import OUT
from probe_ds23_statistical_curvature import OUT as CURVATURE
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    start=time.monotonic()
    with (OUT/(case+'.log')).open('w') as log:
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/probe_ds23_curvature_shape_combination.py'),'--case',case],
            cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=log,stderr=log,timeout=180)
    return dict(case=case,code=r.returncode,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    assert len(read(CURVATURE/'execution.json'))==20 and all(r['code']==0 for r in read(CURVATURE/'execution.json'))
    write(OUT/'protocol.json',dict(cases=cases,workers=2,
        policy='radio curvature promotion, then pre-RF qualified shape mean; revert to curvature policy if either c arm fails',
        no_GPS_selection=True,proposal_pool_is_frozen_from_nominal_mean=True,
        paired_c_observations_labels_aliases_noise_and_budgets_match=True,
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_curvature_shape_combination.py',
            'run_ds23_curvature_shape_combination.py','probe_ds23_causal_shape_ensemble.py','probe_ds23_statistical_curvature.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
