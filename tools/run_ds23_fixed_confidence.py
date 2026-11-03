"""Bounded two-worker confidence ablation on the sealed 20 development scans."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_fixed_confidence import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    started=time.monotonic()
    with (OUT/(case+'.log')).open('w') as log:
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/probe_ds23_fixed_confidence.py'),'--case',case],
            cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=log,stderr=log,timeout=180)
    return dict(case=case,code=r.returncode,seconds=time.monotonic()-started)


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,per_case_timeout_s=180,
        source_sha256=sha(ROOT/'tools/probe_ds23_fixed_confidence.py'),GPS_selection=False,
        same_c_pair_masks_labels_aliases_priors_and_budgets=True))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
