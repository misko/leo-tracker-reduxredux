"""Two bounded numerical workers; no IQ, collection or network access."""

import argparse
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_height import OUT,SIGMAS
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case,scope):
    directory=OUT/scope;directory.mkdir(parents=True,exist_ok=True)
    destination=directory/(case+'.json');source=ROOT/'tools/probe_ds23_height.py';helper=ROOT/'tools/ds23_height_problem.py'
    if destination.exists():
        old=read(destination)
        if old['source_sha256']!=sha(source) or old['helper_sha256']!=sha(helper):
            raise ValueError('changed sources; preserve and version original outputs')
        return dict(case=case,scope=scope,code=0,verified_existing=True,result_sha256=sha(destination))
    started=time.monotonic()
    try:
        with (directory/(case+'.log')).open('w') as log:
            r=subprocess.run([str(ROOT/'.venv/bin/python'),str(source),'--case',case,'--scope',scope],cwd=ROOT,
                env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                stdout=log,stderr=log,timeout=600)
        return dict(case=case,scope=scope,code=r.returncode,seconds=time.monotonic()-started,
                    result_sha256=sha(destination) if destination.exists() else None)
    except subprocess.TimeoutExpired:
        return dict(case=case,scope=scope,code=124,seconds=time.monotonic()-started,timeout_s=600)


def run(stage):
    OUT.mkdir(parents=True,exist_ok=True);cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    if stage=='pilot':tasks=[('DS23-0007','archived'),('DS23-0202','refined')]
    else:tasks=[(case,scope) for case in cases for scope in ('archived','refined')]
    path=OUT/(stage+'_execution.json')
    if path.exists():raise FileExistsError('preserve previous execution receipt')
    write(OUT/(stage+'_protocol.json'),dict(tasks=[dict(case=c,scope=s) for c,s in tasks],workers=2,case_timeout_s=600,
        sample_sha256=sha(SOURCE/'sample.json'),source_sha256=sha(ROOT/'tools/probe_ds23_height.py'),
        helper_sha256=sha(ROOT/'tools/ds23_height_problem.py'),height_SD_hypotheses_m=SIGMAS,
        height_prior_mean_m=0,height_mean_engineering_bounds_m=[-500,9000],selection_uses_RF_not_GPS=True,
        full20_development_cases_not_full_DS23=True,reference_position_used=False,
        original_data_masks_candidate_bank_and_other_priors_preserved=True,
        fit_budget=dict(phase_and_height_rounds=5,steps=48,start_east_north_km=[0,0]),
        no_IQ_reread_or_RF_collection=True))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,*task):task for task in tasks}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:
                case,scope=futures[future];r=dict(case=case,scope=scope,code=1,error=repr(error))
            receipts.append(r);write(path,receipts);print(r,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['pilot','cohort'],required=True)
    run(parser.parse_args().stage)
