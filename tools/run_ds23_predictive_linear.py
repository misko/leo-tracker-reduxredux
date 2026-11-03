"""Bounded cohort test of two predeclared linear-prediction evidence policies."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_predictive_linear import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    path=OUT/(case+'.json');source=ROOT/'tools/probe_ds23_predictive_linear.py'
    if path.exists():
        r=read(path)
        assert r['source_sha256']==sha(source)
        assert r['helper_sha256']==sha(ROOT/'tools/ds23_predictive_linear.py')
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
        sample_sha256=sha(SOURCE/'sample.json'),source_sha256=sha(ROOT/'tools/probe_ds23_predictive_linear.py'),
        helper_sha256=sha(ROOT/'tools/ds23_predictive_linear.py'),policies=['all_linear','cross_rx_linear'],
        minimum_new_track_points=6,one_fixed_c0_extension_label_alias_per_track=True,
        no_GPS_selection_no_IQ_reread=True,original_curved_IDs_masks_labels_aliases_other_priors_preserved=True,
        phase_rounds=5,position_steps=48,phase_convergence_gate_s=.01,
        same_additional_evidence_both_c_arms=True,paired_failure_keeps_previous_pair=True,
        shared_calibration_covariance_conditional_on_curved_Gamma_means=True,
        unweighted_linear_predictive_Gaussian_likelihood=True,
        unseen_noise_inverse_precision_mean=2.,new_curve_constant_sigma_hz=300.,
        covariance_approximation_not_calibrated_posterior=True,
        cohort_is_original20_development_scans_not_full_DS23=True))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,error=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
