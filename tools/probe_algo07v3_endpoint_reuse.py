"""Alternate complete screens while gathering each lower orbital endpoint once."""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

import algo07v3_preendpoint_phase_oracle as oracle
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import residual_screen, screen_geometry
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research import orbit_phase_geometry as owned
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


def operations():
    original = inspect.getsource(oracle.phase_shifted_states)
    changed = original
    before = ('        values = source[rows, index] + fraction[:, :, None] * (\n'
              '            source[rows, index + 1] - source[rows, index]\n'
              '        )')
    after = ('        lower = source[rows, index]\n'
             '        values = lower + fraction[:, :, None] * (source[rows, index + 1] - lower)\n'
             '        del lower')
    if changed.count(before) != 1:
        raise ValueError('Review endpoint source boundary')
    changed = changed.replace(before, after)
    functions = {}
    for label, source in (('baseline', original), ('candidate', changed)):
        # Use the owned snapshot type on both sides; a separately imported
        # oracle class would trigger unnecessary bank validation in the control.
        scope = dict(vars(owned))
        exec(compile(source, f'<endpoint-{label}>', 'exec'), scope)
        functions[label] = scope['phase_shifted_states']
    return functions, dict(baseline=original, candidate=changed)


@contextmanager
def projection(operation):
    original = screen_geometry.phase_shifted_states
    try:
        screen_geometry.phase_shifted_states = operation
        yield
    finally:
        screen_geometry.phase_shifted_states = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__), Path(oracle.__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue, expected = evidence['catalogue'], evidence['audit']['residual_screen']['screen']
    before = fingerprint((packet, catalogue))
    functions, sources = operations()
    for label, source in sources.items():
        (root / f'{label}.py').write_text(source)
    (root / 'plan.json').write_text(json.dumps(dict(bindings=bindings, repeats=3,
        cpus=list(os.sched_getaffinity(0)), blas_threads=1, runtime_modified=False), indent=2)+'\n')
    rows = []
    for pair in range(3):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            callbacks = []
            with projection(functions[side]):
                began, cpu = time.perf_counter(), time.process_time()
                result = residual_screen.screen_candidates(
                    packet, catalogue, SearchRegion(tuple(request['search_center'])),
                    on_target=callbacks.append)
                elapsed, used = time.perf_counter() - began, time.process_time() - cpu
            exact = (fingerprint(result) == fingerprint(expected)
                     and fingerprint(callbacks) == fingerprint(expected['targets']))
            unchanged = before == fingerprint((packet, catalogue))
            row = dict(pair=pair, side=side, seconds=elapsed, cpu_seconds=used,
                       exact=exact, unchanged_inputs=unchanged)
            rows.append(row)
            (root / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2)+'\n')
            print(json.dumps(row), flush=True)
            assert exact and unchanged, 'Complete screen mismatch; retain failed receipt'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
               for p, digest in bindings.items())
    means = {side: {k: statistics.mean(r[k] for r in rows if r['side'] == side)
                    for k in ('seconds', 'cpu_seconds')} for side in ('baseline', 'candidate')}
    result = dict(rows=rows, means=means, exact=True, bindings=bindings,
                  scientific_receipt=saved['sha256'], full_pipeline_speedup=None,
                  runtime_modified=False)
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(means=means)), flush=True)


if __name__ == '__main__':
    main()
