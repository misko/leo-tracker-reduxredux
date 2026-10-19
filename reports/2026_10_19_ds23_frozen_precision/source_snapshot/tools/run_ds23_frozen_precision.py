"""Bounded two-worker frozen-precision experiment on the sealed cohort."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_frozen_precision import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    path=OUT/(case+'.json');source=ROOT/'tools/probe_ds23_frozen_precision.py'
    if path.exists():
        r=read(path)
        assert r['source_sha256']==sha(source)
        assert r['helper_sha256']==sha(ROOT/'tools/ds23_frozen_precision.py')
        return dict(case=case,code=0,verified_existing=True,result_sha256=sha(path))
    started=time.monotonic()
    try:
        with (OUT/(case+'.log')).open('w') as log:
            result=subprocess.run([str(ROOT/'.venv/bin/python'),str(source),'--case',case],cwd=ROOT,
                env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                stdout=log,stderr=log,timeout=180)
        return dict(case=case,code=result.returncode,seconds=time.monotonic()-started,
            result_sha256=sha(path) if path.exists() else None)
    except subprocess.TimeoutExpired:
        return dict(case=case,code=124,seconds=time.monotonic()-started)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'execution.json').exists():raise FileExistsError('preserve previous numerical receipt')
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,case_timeout_s=180,
        sample_sha256=sha(SOURCE/'sample.json'),source_sha256=sha(ROOT/'tools/probe_ds23_frozen_precision.py'),
        helper_sha256=sha(ROOT/'tools/ds23_frozen_precision.py'),
        volume_weights=[1.,0.],frozen_precisions_from_incumbent_c0=True,
        no_GPS_selection_no_IQ_reread=True,same_observations_labels_aliases_prior_coordinates=True,
        same_c0_derived_precisions_both_arms=True,phase_rounds=5,position_steps=48,
        phase_reference_convergence_gate_s=.01,paired_failure_keeps_previous_pair=True,
        cohort_is_original20_development_scans_not_full_DS23=True))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,error=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
