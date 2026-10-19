"""Bounded two-worker robust predictive controls on the original sealed cohort."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_robust_predictive_linear import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    path=OUT/(case+'.json');source=ROOT/'tools/probe_ds23_robust_predictive_linear.py'
    if path.exists():
        r=read(path)
        assert r['source_sha256']==sha(source)
        assert r['helper_sha256']==sha(ROOT/'tools/ds23_robust_predictive_linear.py')
        return dict(case=case,code=0,verified_existing=True,result_sha256=sha(path))
    started=time.monotonic()
    try:
        with (OUT/(case+'.log')).open('w') as log:
            result=subprocess.run([str(ROOT/'.venv/bin/python'),str(source),'--case',case],cwd=ROOT,
                env=dict(os.environ,PYTHONPATH='src:tools',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),
                stdout=log,stderr=log,timeout=300)
        return dict(case=case,code=result.returncode,seconds=time.monotonic()-started,
            result_sha256=sha(path) if path.exists() else None)
    except subprocess.TimeoutExpired:
        return dict(case=case,code=124,seconds=time.monotonic()-started)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'execution.json').exists():raise FileExistsError('preserve previous numerical receipt')
    cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(OUT/'protocol.json',dict(cases=cases,workers=2,case_timeout_s=300,
        sample_sha256=sha(SOURCE/'sample.json'),source_sha256=sha(ROOT/'tools/probe_ds23_robust_predictive_linear.py'),
        helper_sha256=sha(ROOT/'tools/ds23_robust_predictive_linear.py'),
        policies=['student_noise','student_noise_and_bias'],noise_Student_degrees=4.,bias_Student_degrees=4.,
        noise_variance_matches_previous_Gaussian_2_sigma_squared=True,new_bias_variance_hz2=300.**2,
        phase_rounds=5,position_steps=48,phase_convergence_gate_s=.01,predictive_precision_gate_log_change=1e-4,
        original_Gaussian_extension_IDs_labels_aliases_and_c_pair_evidence_preserved=True,
        curved_calibration_no_linear_feedback=True,no_GPS_selection_no_IQ_reread=True,
        paired_failure_keeps_curved_incumbent_pair_without_trimming=True,
        cohort_is_original20_development_scans_not_full_DS23=True))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,error=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
