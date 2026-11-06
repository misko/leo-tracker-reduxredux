"""Profile a complete prepared residual screen without multiprocessing tracing."""

import argparse
import cProfile
import hashlib
import json
import os
import pstats
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import residual_screen
from leo.analysis.localization_v3.region import SearchRegion
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store

PARTS = ('ecef_states', 'phase_frequency_grids', 'profile_rate', 'paired_phase_frequency',
         'components', 'marginal', 'batch_noise_screen')


@contextmanager
def observe(rows):
    originals = [(name, getattr(residual_screen, name)) for name in PARTS]
    try:
        for name, operation in originals:
            def invoke(*args, name=name, operation=operation, **kwargs):
                began = time.perf_counter()
                try:
                    return operation(*args, **kwargs)
                finally:
                    rows[name]['seconds'] += time.perf_counter() - began
                    rows[name]['calls'] += 1
            setattr(residual_screen, name, invoke)
        yield
    finally:
        for name, operation in originals:
            setattr(residual_screen, name, operation)


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
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request,
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue, expected = evidence['catalogue'], evidence['audit']['residual_screen']['screen']
    before = fingerprint((packet, catalogue))
    rows = defaultdict(lambda: dict(seconds=0., calls=0))
    profiler, callbacks = cProfile.Profile(), []
    with observe(rows):
        began = time.perf_counter()
        profiler.enable()
        try:
            actual = residual_screen.screen_candidates(
                packet, catalogue, SearchRegion(tuple(request['search_center'])),
                on_target=lambda target: callbacks.append(fingerprint(target)))
        finally:
            profiler.disable()
        elapsed = time.perf_counter() - began
    profiler.dump_stats(root / 'screen.pstats')
    stats = pstats.Stats(profiler)
    functions = [dict(file=k[0], line=k[1], function=k[2], calls=v[1], self_seconds=v[2],
                      cumulative_seconds=v[3]) for k, v in stats.stats.items()]
    functions.sort(key=lambda r: r['self_seconds'], reverse=True)
    accounting_valid = (sum(r['self_seconds'] for r in functions) <= elapsed * 1.01
                        and all(r['self_seconds'] <= r['cumulative_seconds'] + 1e-9
                                for r in functions))
    exact = (fingerprint(actual) == fingerprint(expected)
             and callbacks == [fingerprint(t) for t in expected['targets']])
    unchanged = before == fingerprint((packet, catalogue))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = dict(parts=dict(rows), seconds=elapsed, functions=functions, exact=exact,
                  unchanged_inputs=unchanged, accounting_valid=accounting_valid,
                  bindings=bindings, scientific_receipt=saved['sha256'],
                  targets=len(packet['targets']), catalogue=len(catalogue['elements']),
                  target_points=[len(t['times_s']) for t in packet['targets']],
                  runtime_modified=False, full_pipeline_speedup=None)
    (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('parts', 'seconds', 'exact', 'accounting_valid',
                                          'targets', 'target_points')}, indent=2))
    assert exact and unchanged and accounting_valid


if __name__ == '__main__':
    main()
