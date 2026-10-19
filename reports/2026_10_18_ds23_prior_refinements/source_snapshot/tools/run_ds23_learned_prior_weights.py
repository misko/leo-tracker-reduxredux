"""Two bounded workers for prespecified learned-prior weight ablations."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_learned_prior_weights import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    start=time.monotonic()
    with (OUT/(case+'.log')).open('w') as stream:
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/probe_ds23_learned_prior_weights.py'),'--case',case],
            cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=stream,stderr=stream,timeout=240)
    return dict(case=case,code=r.returncode,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,methods=['unit','confidence_only'],
        comparator='history_calibrated_phase mean_and_distribution with receiver-support powers',
        priors_from_earlier_TLE_history_only=True,GPS_selection=False,
        first_round_data_and_c_pair_budgets_matched=True,
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_learned_prior_weights.py',
            'run_ds23_learned_prior_weights.py','probe_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
