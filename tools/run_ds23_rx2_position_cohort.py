"""Run ready cases with bounded matched position fits, preserving all receipts."""

import argparse
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from probe_ds23_rx2_measurement_position import METHODS
from remeasure_ds23_rx2_cohort import OUT
from run_algo01_ds23_sample import ROOT, read, write, sha


def worker(case):
    started = time.monotonic()
    source = ROOT / 'tools/probe_ds23_rx2_measurement_position.py'
    results = []
    for method in METHODS:
        path = OUT / (case+'_'+method+'_position.json')
        if path.exists():
            saved = read(path)
            if saved['source_sha256'] != sha(source) or saved['refined_sha256'] != sha(OUT / (case+'_refined.json')):
                raise ValueError('changed position source or measurement input; preserve and version existing output')
            results.append(dict(method=method, code=0, verified_existing=True, sha256=sha(path)))
            continue
        with (OUT / (case+'_'+method+'_position.log')).open('w') as log:
            result = subprocess.run([str(ROOT / '.venv/bin/python'), str(source), '--case', case, '--method', method],
                cwd=ROOT, env=dict(os.environ, PYTHONPATH='src:tools', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'),
                stdout=log, stderr=log, timeout=420)
        results.append(dict(method=method, code=result.returncode, sha256=sha(path) if path.exists() else None))
    return dict(case=case, code=max(r['code'] for r in results), methods=results, seconds=time.monotonic()-started)


def run(cases):
    cases = cases or [r['case'] for r in read(OUT / 'protocol.json')['cases'] if (OUT / (r['case']+'_refined.json')).exists()]
    number = 0
    while (OUT / f'position_execution_{number:02d}.json').exists():
        number += 1
    path = OUT / f'position_execution_{number:02d}.json'
    write(OUT / f'position_protocol_{number:02d}.json', dict(cases=cases, workers=2, method_timeout_s=420,
        methods=METHODS, runner_sha256=sha(ROOT / 'tools/run_ds23_rx2_position_cohort.py'),
        source_sha256=sha(ROOT / 'tools/probe_ds23_rx2_measurement_position.py'),
        selection_is_ready_sealed_measurements_not_geographic_error=True))
    receipts = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker, case): case for case in cases}
        for future in as_completed(futures):
            try:
                receipt = future.result()
            except Exception as error:
                receipt = dict(case=futures[future], code=1, error=repr(error))
            receipts.append(receipt)
            write(path, receipts)
            print(receipt, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', nargs='+')
    run(parser.parse_args().cases)
