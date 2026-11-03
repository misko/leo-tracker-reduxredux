"""Bounded two-worker numerical evaluation; no RF acquisition or IQ read."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from probe_ds23_rx1_prediction_cohort import OUT
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, read, write, sha


def worker(case):
    source = ROOT / 'tools/probe_ds23_rx1_prediction_cohort.py'
    destination = OUT / (case + '.json')
    digest = sha(source)
    if destination.exists() and read(destination)['source_sha256'] == digest:
        return dict(case=case, code=0, verified_existing_result=True, result_sha256=sha(destination))
    started = time.monotonic()
    try:
        with (OUT / (case + '.log')).open('w') as log:
            r = subprocess.run([str(ROOT / '.venv/bin/python'), str(source), '--case', case],
                cwd=ROOT, env=dict(os.environ, PYTHONPATH='src:tools', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'),
                stdout=log, stderr=log, timeout=420)
        return dict(case=case, code=r.returncode, seconds=time.monotonic()-started,
            result_sha256=sha(destination) if destination.exists() else None)
    except subprocess.TimeoutExpired:
        return dict(case=case, code=124, timeout_seconds=420, seconds=time.monotonic()-started)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [r['dataset_label'] for r in read(SOURCE / 'sample.json')['selected']]
    write(OUT / 'protocol.json', dict(cases=cases, workers=2, case_timeout_s=420,
        source_sha256=sha(ROOT / 'tools/probe_ds23_rx1_prediction_cohort.py'),
        dependency_sha256=sha(ROOT / 'tools/probe_ds23_dense_receiver_prediction.py'),
        original_twenty_development_scans=True, no_GPS_selection=True, no_IQ_reads=True,
        fixed_policy=dict(receiver=1, extra_sigma_hz=100, spacing_s=10, width_s=5,
            largest_cross_RX_families=3, reciprocal_RX_prediction=True,
            require_aggregate_prediction_gain_both_receivers=True, require_RF_improvement_and_paired_gates=True)))
    receipts = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker, case): case for case in cases}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception as error:
                r = dict(case=futures[future], code=1, reason=repr(error))
            receipts.append(r)
            write(OUT / 'execution.json', receipts)
            print(r, flush=True)


if __name__ == '__main__':
    run()
