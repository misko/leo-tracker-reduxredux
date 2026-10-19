"""Bounded numerical workers for the carrier-rate cohort and RX prediction probes."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_shared_rate import OUT as RATE
from probe_ds23_receiver_prediction import OUT as PREDICTION
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha

PREDICTION_CASES=['DS23-0217','DS23-0257','DS23-0273','DS23-0274']


def worker(task):
    method,case=task;directory,tool=(RATE,'probe_ds23_shared_rate.py') if method=='rate' else (PREDICTION,'probe_ds23_receiver_prediction.py')
    path=directory/(case+'.json');digest=sha(ROOT/'tools'/tool)
    if path.exists() and read(path)['source_sha256']==digest:
        return dict(method=method,case=case,code=0,validated_existing_result=True,result_sha256=sha(path))
    started=time.monotonic()
    with (directory/(case+'.log')).open('w') as log:
        result=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools'/tool),'--case',case],cwd=ROOT,
            env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=log,stderr=log,timeout=480)
    return dict(method=method,case=case,code=result.returncode,seconds=time.monotonic()-started)


def run():
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    for directory,tool,selected in [(RATE,'probe_ds23_shared_rate.py',cases),(PREDICTION,'probe_ds23_receiver_prediction.py',PREDICTION_CASES)]:
        directory.mkdir(parents=True,exist_ok=True)
        write(directory/'protocol.json',dict(cases=selected,workers=2,case_timeout_s=480,
            source_sha256=sha(ROOT/'tools'/tool),GPS_used_for_inference_or_selection=False,
            region_center=[37.906,-122.545],box_width_km=25,
            prediction_case_choice='three ongoing low-band failures plus smallest-fragment high-band case in the sealed sample',
            c_pair_full_fit_data_priors_and_budgets_match=True))
    tasks=[('prediction',c) for c in PREDICTION_CASES]+[('rate',c) for c in cases]
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,t):t for t in tasks}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(method=futures[future][0],case=futures[future][1],code=1,reason=repr(error))
            receipts.append(r)
            for directory,method in ((RATE,'rate'),(PREDICTION,'prediction')):
                write(directory/'execution.json',[r for r in receipts if r['method']==method])
            print(r,flush=True)


if __name__=='__main__':run()
