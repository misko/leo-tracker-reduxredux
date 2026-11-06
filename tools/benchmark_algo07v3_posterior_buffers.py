"""Alternating complete DS26 training fits for the external posterior scratch buffers."""

import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path

from benchmark_algo07v3_training_kernel import trial
from probe_algo07v3_posterior_buffers import candidate_function, reference, training_inputs

from leo.operations.localization_v3_job import runtime_versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-root', type=Path, required=True)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=2)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    expected_paths = {a: args.expected_root / f'{a}-0-candidate.json' for a in ('c0', 'fitted_c')}
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path(reference.__file__), Path('tools/benchmark_algo07v3_training_kernel.py'),
             Path('tools/probe_algo07v3_posterior_buffers.py'),
             Path('tools/probe_algo07v3_annotation_arms.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'), *expected_paths.values()]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the frozen numerical runtime')
    candidate, original, changed = candidate_function('buffers')
    (args.output / 'original.py').write_text(original)
    (args.output / 'candidate.py').write_text(changed)
    (args.output / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
        phase_rounds=5, optimizer_iterations=48, target=1, fold=1,
        repeats=args.repeats, production_modified=False), indent=2) + '\n')
    rows = []
    for arm in ('c0', 'fitted_c'):
        expected = json.loads(expected_paths[arm].read_bytes())
        assert expected['exact'] and expected['arm'] == arm
        for pair in range(args.repeats):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                d, keep, receipt, seed, split = training_inputs(request)
                operation = reference.hierarchical_bound if side == 'baseline' else candidate
                result = trial(d, keep, arm, operation)
                row = dict(arm=arm, pair=pair, side=side, **result,
                           exact=result['signature'] == expected['signature'],
                           scientific_receipt=receipt, seed=seed, split=split)
                rows.append(row)
                (args.output / f'{arm}-{pair}-{side}.json').write_text(
                    json.dumps(row, indent=2) + '\n')
                print(json.dumps({k: row[k] for k in ('arm', 'pair', 'side', 'seconds',
                                                     'cpu_seconds', 'exact')}), flush=True)
                if not row['exact']:
                    raise ValueError('Complete training fit differs from prior qualified evidence')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {arm: {side: {key: statistics.mean(r[key] for r in rows
                                              if r['arm'] == arm and r['side'] == side)
                          for key in ('seconds', 'cpu_seconds')}
                   for side in ('baseline', 'candidate')} for arm in ('c0', 'fitted_c')}
    (args.output / 'result.json').write_text(json.dumps(dict(
        rows=rows, means=means, bindings=bindings, exact=True,
        prepared_training_benchmark=True, full_pipeline_speedup=None,
        production_modified=False), indent=2) + '\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
