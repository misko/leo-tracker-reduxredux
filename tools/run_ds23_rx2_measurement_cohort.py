"""Two bounded numerical/read workers; root can read, outputs remain user-owned."""

import argparse
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from remeasure_ds23_rx2_cohort import OUT
from run_algo01_ds23_sample import ROOT, read, write, sha


def worker(case, stage):
    suffix = 'qualification' if stage == 'qualify' else 'refined'
    destination = OUT / (case+'_'+suffix+'.json')
    source = ROOT / 'tools/remeasure_ds23_rx2_cohort.py'
    fitter = ROOT / 'tools/fast_local_pilot_refinement.py'
    if destination.exists():
        saved = read(destination)
        if (saved['source_sha256'] != sha(source) or saved['refinement_source_sha256'] != sha(fitter)
                or saved['plan_sha256'] != sha(OUT / (case+'_plan.json'))):
            raise ValueError('existing result has different source or sealed plan; preserve and version it')
        return dict(case=case, stage=stage, code=0, verified_existing=True, result_sha256=sha(destination))
    started = time.monotonic()
    temporary = destination.with_suffix('.incomplete')
    command = ['sudo', '-n', '/usr/bin/timeout', '--kill-after=10s', '900s', '/usr/bin/env',
        'PYTHONPATH=src:tools', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
        str(ROOT / '.venv/bin/python'), str(source), '--stage', stage, '--case', case]
    with temporary.open('w') as output, (OUT / (case+'_'+suffix+'.log')).open('w') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=log, timeout=930)
    receipt = dict(case=case, stage=stage, code=result.returncode, seconds=time.monotonic()-started,
        case_timeout_s=900, outputs_created_by_non_root_orchestrator=True)
    if result.returncode == 0:
        saved = read(temporary)
        if not saved['all_sealed_requests_measured'] or saved['qualification_only'] != (stage=='qualify'):
            raise ValueError('completed process did not prove requested coverage')
        temporary.rename(destination)
        receipt['result_sha256'] = sha(destination)
    return receipt


def run(stage, cases):
    if cases is None:
        cases = (['DS23-0274', 'DS23-0007', 'DS23-0257'] if stage=='qualify'
                 else [r['case'] for r in read(OUT / 'protocol.json')['cases']])
    path = OUT / (stage+'_execution.json')
    if path.exists():
        raise FileExistsError('preserve prior execution receipt before a new attempt')
    write(OUT / (stage+'_runner_protocol.json'), dict(cases=cases, workers=2, timeout_s=900,
        runner_sha256=sha(ROOT / 'tools/run_ds23_rx2_measurement_cohort.py'),
        source_sha256=sha(ROOT / 'tools/remeasure_ds23_rx2_cohort.py'),
        fitter_sha256=sha(ROOT / 'tools/fast_local_pilot_refinement.py'),
        bounded_existing_corpus_only=True))
    receipts = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker, case, stage): case for case in cases}
        for future in as_completed(futures):
            try:
                receipt = future.result()
            except Exception as error:
                receipt = dict(case=futures[future], stage=stage, code=1, error=repr(error))
            receipts.append(receipt)
            write(path, receipts)
            print(receipt, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('qualify', 'measure'), required=True)
    parser.add_argument('--cases', nargs='+')
    args = parser.parse_args()
    run(args.stage, args.cases)
