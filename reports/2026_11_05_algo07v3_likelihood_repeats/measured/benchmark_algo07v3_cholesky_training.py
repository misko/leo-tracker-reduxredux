"""Alternate complete hard-case training fits for the external Cholesky probe."""

import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path

import numpy as np
from benchmark_algo07v3_training_kernel import trial
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_cholesky import candidate
from probe_algo07v3_posterior_buffers import training_inputs

from leo.analysis.localization_v3 import hierarchical
from leo.operations.localization_v3_job import runtime_versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/probe_algo07v3_cholesky.py'),
             Path('tools/probe_algo07v3_posterior_buffers.py'),
             Path('tools/benchmark_algo07v3_training_kernel.py'),
             Path('tools/probe_algo07v3_annotation_arms.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    operation, original, changed = candidate()
    (args.output / 'original.py').write_text(original)
    (args.output / 'candidate.py').write_text(changed)
    (args.output / 'plan.json').write_text(json.dumps(dict(bindings=bindings, repeats=2,
        affinity=sorted(os.sched_getaffinity(0)), blas_threads=1, phase_rounds=5,
        optimizer_iterations=48, target_index=1, fold_index=1), indent=2) + '\n')
    rows = []
    for arm in ('c0', 'fitted_c'):
        expected = None
        for pair in range(2):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                d, keep, receipt, seed, split = training_inputs(request)
                before = fingerprint((d['node'], keep))
                function = hierarchical.hierarchical_bound if side == 'baseline' else operation
                result = trial(d, keep, arm, function)
                if expected is None:
                    expected = result['signature']
                row = dict(arm=arm, pair=pair, side=side, **result,
                           exact=result['signature'] == expected, scientific_receipt=receipt,
                           seed=seed, split=split, training_points=int(np.sum(keep)))
                rows.append(row)
                (args.output / f'{arm}-{pair}-{side}.json').write_text(
                    json.dumps(row, indent=2) + '\n')
                print(json.dumps({k: row[k] for k in ('arm', 'pair', 'side', 'seconds',
                                                     'cpu_seconds', 'exact')}), flush=True)
                assert row['exact'], 'Complete training fit differs; retain failed receipt'
                assert before == fingerprint((d['node'], keep))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {arm: {side: {k: statistics.mean(r[k] for r in rows
                                           if r['arm'] == arm and r['side'] == side)
                          for k in ('seconds', 'cpu_seconds')}
                   for side in ('baseline', 'candidate')} for arm in ('c0', 'fitted_c')}
    result = dict(rows=rows, means=means, exact=True, bindings=bindings,
                  full_pipeline_speedup=None, production_modified=False)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
