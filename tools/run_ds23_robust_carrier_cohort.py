"""Bounded two-worker robust shared-carrier controls on the same twenty cases."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from probe_ds23_robust_carrier_constants import OUT
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, read, write, sha


def worker(case):
    directory = OUT/'incumbent/baseline'
    destination = directory/(case+'.json')
    source = ROOT/'tools/probe_ds23_robust_carrier_constants.py'
    digest = sha(source)
    if destination.exists() and read(destination)['source_sha256'] == digest:
        return dict(case=case, code=0, verified_existing_result=True, result_sha256=sha(destination))
    started = time.monotonic()
    try:
        with (directory/(case+'.log')).open('w') as log:
            r = subprocess.run([str(ROOT/'.venv/bin/python'), str(source), '--case', case, '--scope', 'incumbent'],
                cwd=ROOT, env=dict(os.environ, PYTHONPATH='src:tools', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'),
                stdout=log, stderr=log, timeout=420)
        return dict(case=case, code=r.returncode, seconds=time.monotonic()-started,
            result_sha256=sha(destination) if destination.exists() else None)
    except subprocess.TimeoutExpired:
        return dict(case=case, code=124, seconds=time.monotonic()-started, timeout_seconds=420)


def run():
    directory = OUT/'incumbent/baseline'
    directory.mkdir(parents=True, exist_ok=True)
    cases = [r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    write(directory/'protocol.json', dict(cases=cases, workers=2, case_timeout_s=420,
        source_sha256=sha(ROOT/'tools/probe_ds23_robust_carrier_constants.py'),
        prior_source_sha256=sha(ROOT/'tools/ds23_robust_carrier_prior.py'), sample_sha256=sha(SOURCE/'sample.json'),
        phase_prior_unchanged=True, prior_nu3_for_active_fragment_contrasts=True,
        inactive_independent_priors_collapsed_exactly=True, sigma_candidates_hz=[100, 30],
        original_Gaussian_hypotheses_retained=True, original_twenty_development_cases=True,
        no_GPS_selection=True, no_RF_or_IQ_read=True, matched_c_pairs_from_regional_center=True))
    receipts = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker, c):c for c in cases}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception as error:
                r = dict(case=futures[future], code=1, reason=repr(error))
            receipts.append(r)
            write(directory/'execution.json', receipts)
            print(r, flush=True)


if __name__ == '__main__':
    run()
