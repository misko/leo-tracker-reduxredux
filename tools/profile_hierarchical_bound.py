"""Capture and compare real hierarchical likelihood calls, without position selection."""

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np


def capture(source, inventory, output):
    source = source.resolve()
    sys.path[:0] = [str(source/'tools'), str(source/'src')]
    import dsx01_hierarchical_bound as module

    original = module.hierarchical_bound
    output.mkdir(parents=True, exist_ok=False)
    rows = []

    def recorded(raw, features, sigma, groups, **kwargs):
        start = time.perf_counter()
        result = original(raw, features, sigma, groups, **kwargs)
        elapsed = time.perf_counter()-start
        name = f'call-{len(rows):03d}.npz'
        arrays = dict(raw=raw, features=features, sigma=sigma, groups=groups)
        arrays.update({'kw_'+k: v for k, v in kwargs.items() if v is not None})
        arrays.update({'result_'+k: v for k, v in result.items()})
        np.savez_compressed(output/name, **arrays)
        rows.append(dict(path=name, seconds=elapsed, shape=list(np.shape(features)),
                         sha256=hashlib.sha256((output/name).read_bytes()).hexdigest()))
        return result

    module.hierarchical_bound = recorded
    from diagnose_all_large_tracks import context

    d = context(json.loads(inventory.read_text()))
    for arm in ('c0', 'fitted_c'):
        problem, incumbent = d['problems'][arm]
        for point in (np.zeros(2), incumbent, np.array([5., -5.])):
            problem.calculate(point)
    receipt = dict(calls=rows, input_inventory=str(inventory),
                   input_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(),
                   source=str(source), implementation_sha256=hashlib.sha256(
                       Path(module.__file__).read_bytes()).hexdigest(),
                   positions='center, incumbent, fixed (5,-5) km; both arms',
                   scope='likelihood calls, not optimization or localization replay')
    (output/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(dict(calls=len(rows), shapes=[r['shape'] for r in rows])))


def load_function(path):
    spec = importlib.util.spec_from_file_location('bound_benchmark', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.hierarchical_bound


def measure(fixture, baseline, candidate, output, repeats):
    receipt = json.loads((fixture/'capture.json').read_text())
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != receipt['implementation_sha256']:
        raise ValueError('Captured baseline code changed')
    functions = [load_function(p) for p in (baseline, candidate)]
    rows = []
    for row in receipt['calls']:
        path = fixture/row['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Captured arrays changed')
        with np.load(path, allow_pickle=False) as saved:
            args = [saved[k] for k in ('raw', 'features', 'sigma', 'groups')]
            kwargs = {k[3:]: saved[k] for k in saved.files if k.startswith('kw_')}
            expected = {k[7:]: saved[k] for k in saved.files if k.startswith('result_')}
        timings = [[], []]
        exact = True
        differences = []
        for repeat in range(repeats):
            for side in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                start = time.perf_counter()
                result = functions[side](*args, **kwargs)
                timings[side].append(time.perf_counter()-start)
                if result.keys() != expected.keys():
                    raise ValueError('Output inventory differs')
                for key in result:
                    if not np.array_equal(result[key], expected[key]):
                        exact = False
                        differences.append(dict(side=side, field=key, maximum_delta=float(
                            np.max(np.abs(np.asarray(result[key])-expected[key])))))
        rows.append(dict(path=row['path'], shape=row['shape'], exact=exact,
                         baseline_seconds=timings[0], candidate_seconds=timings[1],
                         differences=differences))
    result = dict(passed=bool(rows) and all(r['exact'] for r in rows), repeats=repeats,
                  alternating_order=True, rows=rows, tolerance=0,
                  baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
                  candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'], calls=len(rows),
                         baseline_median_sum=sum(np.median(r['baseline_seconds']) for r in rows),
                         candidate_median_sum=sum(
                             np.median(r['candidate_seconds']) for r in rows))))
    if not result['passed']:
        raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='command', required=True)
    c = s.add_parser('capture')
    for name in ('source', 'inventory', 'output'):
        c.add_argument('--'+name, type=Path, required=True)
    m = s.add_parser('measure')
    for name in ('fixture', 'baseline', 'candidate', 'output'):
        m.add_argument('--'+name, type=Path, required=True)
    m.add_argument('--repeats', type=int, default=5, choices=range(1, 21))
    a = p.parse_args()
    if a.command == 'capture':
        capture(a.source, a.inventory, a.output)
    else:
        measure(a.fixture, a.baseline, a.candidate, a.output, a.repeats)


if __name__ == '__main__':
    main()
