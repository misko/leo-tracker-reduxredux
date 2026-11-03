"""Bounded independent simulation cohorts; no RF acquisition or IQ access."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_gate_null import OUT,SIZES,KINDS,AMPLITUDES
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    path=OUT/(case+'.json');source=ROOT/'tools/probe_ds23_gate_null.py'
    if path.exists():
        r=read(path)
        assert r['source_sha256']==sha(source) and r['helper_sha256']==sha(ROOT/'tools/ds23_gate_null.py') and r['sizes']==SIZES
        return dict(case=case,code=0,verified_existing=True,result_sha256=sha(path))
    started=time.monotonic()
    try:
        with (OUT/(case+'.log')).open('w') as log:
            r=subprocess.run([str(ROOT/'.venv/bin/python'),str(source),'--case',case],cwd=ROOT,
                env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                stdout=log,stderr=log,timeout=240)
        return dict(case=case,code=r.returncode,seconds=time.monotonic()-started,
            result_sha256=sha(path) if path.exists() else None)
    except subprocess.TimeoutExpired:return dict(case=case,code=124,seconds=time.monotonic()-started)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'execution.json').exists():raise FileExistsError('preserve previous execution')
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,case_timeout_s=240,sizes=SIZES,
        sample_sha256=sha(SOURCE/'sample.json'),source_sha256=sha(ROOT/'tools/probe_ds23_gate_null.py'),
        helper_sha256=sha(ROOT/'tools/ds23_gate_null.py'),alpha=.05,never_tighten_original_cutoff=True,
        calibration_model='paired fixed-precision prior-mean Gaussian refit',
        independent_evaluation_models=['white','fitted_centered','fitted_plugin'],
        full_precision_checks=['DS23-0074','DS23-0217'],injections=KINDS,amplitudes_RMS_hz=AMPLITUDES,
        calibration_evaluation_power_and_full_precision_seeds_distinct=True,
        common_CFO_noise_for_c0_and_fitted_c=True,no_GPS_threshold_selection=True,
        real_GLRT_observations_never_withheld=True,no_IQ_reread_or_RF_collection=True,
        posterior_conditioned_Gaussian_surrogate_not_full_pipeline_bootstrap=True,
        positions_only_saved_RF_individual_and_causal_stationary_prefix=True,
        no_new_position_optimization_mask_or_identity_search=True))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,error=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
