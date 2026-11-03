"""Two bounded numerical workers for scan217 and three largest residual failures."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_joint_family_search import OUT as JOINT
from probe_ds23_secondary_curves import OUT as CURVES
from run_algo01_ds23_sample import ROOT,write,sha

CASES=['DS23-0217','DS23-0257','DS23-0202','DS23-0273']


def worker(task):
    method,case=task;directory,tool=(JOINT,'probe_ds23_joint_family_search.py') if method=='joint' else (CURVES,'probe_ds23_secondary_curves.py')
    started=time.monotonic()
    # The original scan217 processes were launched with these exact sources.
    if case=='DS23-0217':
        while not (directory/(case+'.json')).exists() and time.monotonic()-started<420:
            time.sleep(1)
        return dict(method=method,case=case,code=0 if (directory/(case+'.json')).exists() else 1,
                    started_before_runner=True,seconds=time.monotonic()-started)
    with (directory/(case+'.log')).open('w') as log:
        result=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools'/tool),'--case',case],cwd=ROOT,
            env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=log,stderr=log,timeout=420)
    return dict(method=method,case=case,code=result.returncode,seconds=time.monotonic()-started)


def run():
    for directory,tool in [(JOINT,'probe_ds23_joint_family_search.py'),(CURVES,'probe_ds23_secondary_curves.py')]:
        directory.mkdir(parents=True,exist_ok=True)
        write(directory/'protocol.json',dict(cases=CASES,source_sha256=sha(ROOT/'tools'/tool),
            workers=2,per_case_timeout_s=420,cases_are_diagnostic_not_a_representative_test_set=True,
            case_selection='ongoing scan217 investigation plus three largest primary c0 errors in the development cohort',
            GPS_used_for_inference_or_algorithm_selection=False,causal_inputs_unchanged=True))
    receipts=[];tasks=[(m,c) for c in CASES for m in ('joint','curves')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,t):t for t in tasks}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(method=futures[future][0],case=futures[future][1],code=1,reason=repr(error))
            receipts.append(r)
            for directory,method in [(JOINT,'joint'),(CURVES,'curves')]:
                write(directory/'execution.json',[r for r in receipts if r['method']==method])
            print(r,flush=True)


if __name__=='__main__':run()
