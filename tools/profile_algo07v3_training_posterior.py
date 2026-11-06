"""Profile one complete training fit and retain its hardest observed posterior input."""

import argparse
import cProfile
import hashlib
import json
import os
import pstats
import time
from pathlib import Path

import numpy as np
from benchmark_algo07v3_training_kernel import kernel, trial
from probe_algo07v3_posterior_buffers import reference, training_inputs

from leo.operations.localization_v3_job import runtime_versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arm', choices=['c0', 'fitted_c'], required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, args.expected, Path(__file__),
             Path(reference.__file__), Path('tools/benchmark_algo07v3_training_kernel.py'),
             Path('tools/probe_algo07v3_posterior_buffers.py'),
             Path('tools/probe_algo07v3_annotation_arms.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the frozen numerical runtime')
    expected = json.loads(args.expected.read_bytes())
    assert expected['arm'] == args.arm and expected['exact']
    d, keep, receipt, seed, split = training_inputs(request)
    calls, hardest = [], {}

    def observed(*positional, **keywords):
        before = time.perf_counter()
        value = reference.hierarchical_bound(*positional, **keywords)
        elapsed = time.perf_counter() - before
        iterations = value['precision_iterations']
        row = dict(seconds=elapsed, shape=positional[1].shape, precision_iterations=iterations)
        calls.append(row)
        rank = iterations, elapsed
        if rank > hardest.get('rank', (-1, -1)):
            hardest.update(rank=rank, call=len(calls) - 1, row=row,
                           positional=[np.array(v, copy=True) for v in positional],
                           keywords={k: np.array(v, copy=True) if isinstance(v, np.ndarray) else v
                                     for k, v in keywords.items()})
        return value

    (args.output / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, arm=args.arm, seed=seed, split=split,
        scientific_receipt=receipt, affinity=sorted(os.sched_getaffinity(0)),
        blas_threads=1, production_modified=False), indent=2) + '\n')
    profiler = cProfile.Profile()
    with kernel(observed):
        profiler.enable()
        result = trial(d, keep, args.arm, observed)
        profiler.disable()
    profiler.dump_stats(args.output / 'training.pstats')
    stats = pstats.Stats(profiler)
    functions = [dict(file=k[0], line=k[1], function=k[2], primitive_calls=v[0],
                      calls=v[1], self_seconds=v[2], cumulative_seconds=v[3])
                 for k, v in stats.stats.items()]
    functions.sort(key=lambda row: row['self_seconds'], reverse=True)
    arrays = {f'argument_{i}': v for i, v in enumerate(hardest['positional'])}
    scalar_keywords = {}
    for k, v in hardest['keywords'].items():
        if isinstance(v, np.ndarray):
            arrays[f'keyword_{k}'] = v
        else:
            scalar_keywords[k] = v
    np.savez(args.output / 'hardest.npz', **arrays)
    (args.output / 'hardest.json').write_text(json.dumps(dict(
        call=hardest['call'], **hardest['row'], scalar_keywords=scalar_keywords,
        arrays_sha256=hashlib.sha256((args.output / 'hardest.npz').read_bytes()).hexdigest()),
        indent=2) + '\n')
    exact = result['signature'] == expected['signature']
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    output = dict(result=result, exact=exact, calls=calls, functions=functions,
                  bindings=bindings, profiled=True, production_modified=False,
                  full_pipeline_speedup=None)
    (args.output / 'profile.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(dict(exact=exact, seconds=result['seconds'], calls=len(calls),
                         hardest=hardest['row'], top=functions[:12]), indent=2), flush=True)
    if not exact:
        raise ValueError('Full profiled training fit differs from prior qualified result')


if __name__ == '__main__':
    main()
