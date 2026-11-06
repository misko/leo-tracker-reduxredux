"""Compare FIFO versus fitted-c-first ordering of the same six queued initial fits.

Complete initial searches retain every hypothesis, numerical budget, callback
value and selected result. Runtime is untouched; source and inputs are bound.
"""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
from pathlib import Path

import algo07v3_preinitialqueue_oracle as oracle
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_initial_queue import cpu, measured_mapper, transform

from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_annotation_training
from leo.storage.localization_v3 import LocalizationV3Store


def fitted_first(operation, tasks):
    """Start fitted-c arms first, then restore the original branch/arm order."""
    tasks = tuple(tasks)
    priority = sorted(range(len(tasks)), key=lambda i: (tasks[i][1] != 'fitted_c', i))
    slots = {task: i for i, task in enumerate(tasks)}
    values = map_annotation_training(lambda slot: operation(tasks[priority[slots[slot]]]), tasks)
    ordered = [None] * len(tasks)
    for index, value in zip(priority, values, strict=True):
        ordered[index] = value
    return ordered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    files = [*Path('src').rglob('*.py'), args.request, Path(__file__), Path(oracle.__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_initial_queue.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared, expected = saved['evidence']['preparation'], saved['evidence']['audit']['initial']
    before = fingerprint(prepared)
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False)+'\n').encode()
    _, _, candidate = transform()
    (root / 'baseline.py').write_text(candidate)
    (root / 'schedule.py').write_text(inspect.getsource(fitted_first))
    (root / 'candidate.py').write_text(candidate)
    (root / 'plan.json').write_text(json.dumps(dict(bindings=bindings, repeats=args.repeats,
        cpus=sorted(os.sched_getaffinity(0)), blas_threads=1, max_workers=3,
        runtime_modified=False, baseline='FIFO queue', candidate='fitted-c-first queue'),
        indent=2)+'\n')
    rows = []
    for pair in range(args.repeats):
        for side in (('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')):
            scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                            hashlib.sha256(noise).hexdigest(), genuine=False)
            blocks, callbacks = [], []
            queued = map_annotation_training if side == 'baseline' else fitted_first
            operation, _, _ = transform(measured_mapper(queued, blocks, queued=True))
            began, used = time.perf_counter(), cpu()
            actual = operation(scan, scan.radio_sigma_hz, on_branch=callbacks.append,
                               map_arms=None)
            elapsed, used = time.perf_counter()-began, cpu()-used
            exact = (fingerprint(actual) == fingerprint(expected)
                     and fingerprint(callbacks) == fingerprint(expected['choices']))
            unchanged = fingerprint(prepared) == before
            row = dict(pair=pair, side=side, seconds=elapsed, cpu_seconds=used,
                       branch_fit_seconds=sum(b['seconds'] for b in blocks),
                       blocks=blocks, exact=exact, unchanged_inputs=unchanged)
            rows.append(row)
            (root / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2)+'\n')
            print(json.dumps({k:v for k,v in row.items() if k != 'blocks'}), flush=True)
            if not exact:
                (root / f'{pair}-{side}-failure.json').write_text(json.dumps(dict(
                    actual=fingerprint(actual), expected=fingerprint(expected),
                    callbacks=fingerprint(callbacks)), indent=2)+'\n')
            assert exact and unchanged, 'Complete initial search or callbacks differ'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {side: {key: statistics.mean(r[key] for r in rows if r['side'] == side)
                    for key in ('seconds', 'cpu_seconds', 'branch_fit_seconds')}
             for side in ('baseline', 'candidate')}
    result = dict(rows=rows, means=means, bindings=bindings, scientific_receipt=saved['sha256'],
                  exact=True, runtime_modified=False, full_pipeline_speedup=None)
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
