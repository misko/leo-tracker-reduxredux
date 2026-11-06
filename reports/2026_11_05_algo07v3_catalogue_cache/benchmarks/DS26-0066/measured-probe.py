"""Alternate complete native preparation plus recovery-catalogue construction.

The candidate extends the existing validated-text parser across these two
stages. Archive reads and fresh mutable SGP4 construction are retained.
"""

import argparse
import functools
import hashlib
import inspect
import json
import os
import statistics
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3 import cpu, resources

from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.localization_v3.tracks import TrackConfig
from leo.application.localization_v3 import prepare_native_scan
from leo.cli.algo07v3 import write
from leo.operations import localization_v3_inputs as inputs
from leo.operations.localization_v3_job import read_bound, runtime_versions
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


class ObservedParser:
    def __init__(self, parser):
        self.parser = parser
        self.calls = 0
        self.seconds = 0.0

    def __call__(self, text):
        began = time.perf_counter()
        try:
            return self.parser(text)
        finally:
            self.calls += 1
            self.seconds += time.perf_counter() - began


def recovery(parser):
    source = inspect.getsource(inputs.prepare_recovery_catalogue)
    scope = dict(vars(inputs), causal_catalogue=functools.partial(
        inputs.causal_catalogue, element_parser=parser))
    exec(compile(source, '<recovery-parser-injection>', 'exec'), scope)
    return scope['prepare_recovery_catalogue']


def trial(document, archive, config, screen, shared):
    parser = ElementParser()
    initial_parser = ObservedParser(parser)
    recovery_parser = ObservedParser(parser if shared else parse_element_sets)
    operation = recovery(recovery_parser)
    before, began = cpu(), time.perf_counter()
    prepared = prepare_native_scan(document, archive, config,
                                  screen_latitude_deg=screen[0],
                                  screen_longitude_deg=screen[1], element_parser=initial_parser)
    prepared_seconds = time.perf_counter() - began
    if prepared['status'] != 'inputs_prepared':
        raise ValueError('Complete native preparation required')
    after_initial = parser.statistics()
    start = time.perf_counter()
    catalogue = operation(archive, prepared['sky']['metadata']['cutoff_utc_ns'])
    recovery_seconds = time.perf_counter() - start
    elapsed, after = time.perf_counter() - began, cpu()
    return dict(seconds=elapsed, preparation_seconds=prepared_seconds,
                recovery_seconds=recovery_seconds,
                cpu_seconds=sum(after) - sum(before),
                initial_parser_seconds=initial_parser.seconds,
                initial_parser_calls=initial_parser.calls,
                recovery_parser_seconds=recovery_parser.seconds,
                recovery_parser_calls=recovery_parser.calls,
                cache_after_initial=after_initial, cache_after_recovery=parser.statistics(),
                elements=len(catalogue['elements']), snapshots=catalogue['snapshot_count'],
                fingerprint=fingerprint(dict(preparation=prepared, catalogue=catalogue)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    if request['runtime'] != runtime_versions():
        raise ValueError('Match the frozen numerical runtime')
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'), Path('tools/profile_algo07v3.py'),
             Path(request['native_input']['path']).parent / 'input-bindings.json']
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=bindings, repeats=args.repeats,
                                   affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                                   runtime_integrated=False, production_modified=False))
    write(root / 'resources-start.json', resources())
    native = read_bound(request['native_input'])
    config = TrackConfig(**read_bound(request['track_config'])['config'])
    archive = TleArchiveReader(Path(request['tle_root']))
    expected, rows = None, []
    for pair in range(args.repeats):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            row = trial(native, archive, config, request['screen_center'], side == 'candidate')
            signature = row.pop('fingerprint')
            if expected is None:
                expected = signature
                write(root / 'expected.json', expected)
            row.update(pair=pair, side=side, exact=signature == expected)
            rows.append(row)
            write(root / 'trials.json', rows)
            print(json.dumps(row), flush=True)
            if not row['exact']:
                raise ValueError('Complete native preparation/catalogue changed')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound sources changed during benchmark')
    means = {s: {k: statistics.mean(r[k] for r in rows if r['side'] == s)
                 for k in ('seconds', 'preparation_seconds', 'recovery_seconds', 'cpu_seconds',
                           'recovery_parser_seconds')} for s in ('baseline', 'candidate')}
    write(root / 'resources-end.json', resources())
    write(root / 'summary.json', dict(exact=True, means=means, executions=len(rows),
                                     full_pipeline_speed_benchmark=False))
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
