"""Two bounded workers for radio-significant curvature promotion."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_statistical_curvature import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    start=time.monotonic()
    with (OUT/(case+'.log')).open('w') as stream:
        r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'tools/probe_ds23_statistical_curvature.py'),'--case',case],
            cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
            stdout=stream,stderr=stream,timeout=240)
    return dict(case=case,code=r.returncode,seconds=time.monotonic()-start)


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,development_probes=['DS23-0217','DS23-0161'],
        rule='additional radio-only nonlinear deltaBIC>=10 versus affine, degree<=4 with >=4 points/coefficient, >=12points, span>=20s, original noise screen',
        current_frozen_family_and_alias_must_agree_in_both_c_arms=True,initial_points_never_removed=True,
        greedy_addition_order='descending radio-only curvature deltaBIC',acceptance='all old and new gates pass in both c arms',
        priors_noise_labels_original_weights_preserved=True,new_fragment_weight='minimum existing active weight in its RF-discovered family',
        no_GPS_selection=True,no_linear_track_calibration=True,
        budgets=dict(phase_rounds=5,position_steps=48,case_timeout_s=240),
        source_sha256={n:sha(ROOT/'tools'/n) for n in ['probe_ds23_statistical_curvature.py','run_ds23_statistical_curvature.py','probe_ds23_history_calibrated_phase.py']}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,reason=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
