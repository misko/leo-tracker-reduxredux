"""Measure a three-worker queue across all six initial branch/arm fits.

Complete initial searches retain every hypothesis, numerical budget, callback
value and selected result. Runtime is untouched; source and inputs are bound.
"""

import argparse
import hashlib
import inspect
import json
import os
import resource
import statistics
import time
from pathlib import Path

import algo07v3_preinitialqueue_oracle as oracle
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_annotation_training, map_initial_arms
from leo.storage.localization_v3 import LocalizationV3Store


def transform(mapper=map_annotation_training):
    source = inspect.getsource(oracle.initial_search)
    before = """    choices = []
    for index, (score, node) in enumerate(selected):
        arms = ('c0', 'fitted_c')
        mapped = (map if map_arms is None else map_arms)(
            lambda arm, node=node: fit_initial_arm(scan, sigma, node, arm,
                                        rounds=rounds, iterations=iterations), arms)
        pair = dict(zip(arms, mapped, strict=True))"""
    after = """    tasks = [(index, arm) for index in range(len(selected))
             for arm in ('c0', 'fitted_c')]
    fitted = list(_map_branches(
        lambda item: fit_initial_arm(scan, sigma, selected[item[0]][1], item[1],
                                     rounds=rounds, iterations=iterations), tasks))
    if len(fitted) != len(tasks):
        raise ValueError('One result per initial branch/arm required')
    choices = []
    for index, (score, node) in enumerate(selected):
        arms = ('c0', 'fitted_c')
        pair = dict(zip(arms, fitted[2*index:2*index+2], strict=True))"""
    if source.count(before) != 1:
        raise ValueError('Initial branch loop changed; review the extraction')
    candidate = source.replace(before, after)
    scope = dict(vars(oracle), _map_branches=mapper)
    exec(compile(candidate, '<initial-branch-queue>', 'exec'), scope)
    return scope['initial_search'], source, candidate


def cpu():
    return sum(r.ru_utime + r.ru_stime for r in (
        resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)))


def measured_mapper(mapper, blocks, *, queued):
    def run(operation, items):
        items = tuple(items)
        branch = len(blocks)

        def measured(item):
            began, used = time.perf_counter(), time.process_time()
            value = operation(item)
            return value, dict(task=item if queued else (branch, item),
                start=began, end=time.perf_counter(),
                cpu_seconds=time.process_time()-used,
                max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

        began = time.perf_counter()
        results = mapper(measured, items)
        blocks.append(dict(seconds=time.perf_counter()-began, tasks=[r[1] for r in results]))
        return [r[0] for r in results]
    return run


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
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared, expected = saved['evidence']['preparation'], saved['evidence']['audit']['initial']
    before = fingerprint(prepared)
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False)+'\n').encode()
    _, source, candidate = transform()
    (root / 'baseline.py').write_text(source)
    (root / 'candidate.py').write_text(candidate)
    (root / 'plan.json').write_text(json.dumps(dict(bindings=bindings, repeats=args.repeats,
        cpus=sorted(os.sched_getaffinity(0)), blas_threads=1, max_workers=3,
        runtime_modified=False), indent=2)+'\n')
    rows = []
    for pair in range(args.repeats):
        for side in (('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')):
            scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                            hashlib.sha256(noise).hexdigest(), genuine=False)
            blocks, callbacks = [], []
            if side == 'baseline':
                operation = oracle.initial_search
                mapper = measured_mapper(map_initial_arms, blocks, queued=False)
            else:
                operation, _, _ = transform(measured_mapper(
                    map_annotation_training, blocks, queued=True))
                mapper = None
            began, used = time.perf_counter(), cpu()
            actual = operation(scan, scan.radio_sigma_hz, on_branch=callbacks.append,
                               map_arms=mapper)
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
