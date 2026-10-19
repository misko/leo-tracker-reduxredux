"""Bounded two-worker shared-carrier controls on all original development cases."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from probe_ds23_shared_carrier_constants import OUT, MODES
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, read, write, sha


def worker(case):
    directory = OUT / 'incumbent/baseline'
    destination = directory / (case + '.json')
    source = ROOT / 'tools/probe_ds23_shared_carrier_constants.py'
    digest = sha(source)
    if destination.exists() and read(destination)['source_sha256'] == digest:
        return dict(case=case, code=0, verified_existing_result=True, result_sha256=sha(destination))
    started = time.monotonic()
    try:
        with (directory / (case + '.log')).open('w') as log:
            r = subprocess.run([str(ROOT / '.venv/bin/python'), str(source), '--case', case,
                '--scope', 'incumbent', '--receiver', 'baseline'], cwd=ROOT,
                env=dict(os.environ, PYTHONPATH='src:tools', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'),
                stdout=log, stderr=log, timeout=420)
        return dict(case=case, code=r.returncode, seconds=time.monotonic()-started,
            result_sha256=sha(destination) if destination.exists() else None)
    except subprocess.TimeoutExpired:
        return dict(case=case, code=124, timeout_seconds=420, seconds=time.monotonic()-started)


def run():
    directory = OUT / 'incumbent/baseline'
    directory.mkdir(parents=True, exist_ok=True)
    cases = [r['dataset_label'] for r in read(SOURCE / 'sample.json')['selected']]
    write(directory / 'protocol.json', dict(cases=cases, workers=2, case_timeout_s=420,
        source_sha256=sha(ROOT / 'tools/probe_ds23_shared_carrier_constants.py'),
        sample_sha256=sha(SOURCE / 'sample.json'), hypotheses=MODES,
        fixed_shared_sigma_hz=300, fixed_fragment_sigmas_hz=[100, 30], reference_RF_hz=11.5e9,
        independent_and_old_rho90_controls=True, original_twenty_development_cases=True,
        no_GPS_selection=True, no_new_RF_or_IQ_read=True,
        candidate_catalogue_observations_masks_aliases_and_other_priors_unchanged=True,
        matched_c_pair_five_rounds_48_steps_from_regional_center=True,
        policy='minimum c0 normalized RF loss among paired-gate-passing hypotheses; incumbent always retained'))
    receipts = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker, c): c for c in cases}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception as error:
                r = dict(case=futures[future], code=1, reason=repr(error))
            receipts.append(r)
            write(directory / 'execution.json', receipts)
            print(r, flush=True)


if __name__ == '__main__':
    run()
