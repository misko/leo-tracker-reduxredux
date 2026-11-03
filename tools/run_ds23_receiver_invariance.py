"""Bounded cohort of in-memory, one-prior-SD receiver perturbations."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from probe_ds23_receiver_invariance import OUT,SCENARIOS
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    path=OUT/(case+'.json');source=ROOT/'tools/probe_ds23_receiver_invariance.py'
    if path.exists():
        r=read(path)
        assert r['source_sha256']==sha(source) and r['helper_sha256']==sha(ROOT/'tools/ds23_calibration_mean.py')
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
    write(OUT/'protocol.json',dict(cases=cases,workers=2,case_timeout_s=240,scenarios=SCENARIOS,
        sample_sha256=sha(SOURCE/'sample.json'),source_sha256=sha(ROOT/'tools/probe_ds23_receiver_invariance.py'),
        helper_sha256=sha(ROOT/'tools/ds23_calibration_mean.py'),receiver_choice='most active original curved probes',
        basis_choice='middle existing receiver smooth column',coefficient_changes_prior_SD=[-1,1],
        mean_translation_control_is_oracle_not_deployable=True,no_GPS_selection=True,
        synthetic_changes_in_memory_only_original_GLRT_values_unchanged=True,
        original_labels_aliases_masks_noise_and_c_pair_inputs_fixed=True,
        five_phase_refreshes_48steps_regional_cold_start=True,
        all_raw_displacements_reported_including_failed_gates=True))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(case=futures[future],code=1,error=repr(error))
            receipts.append(r);write(OUT/'execution.json',receipts);print(r,flush=True)


if __name__=='__main__':run()
