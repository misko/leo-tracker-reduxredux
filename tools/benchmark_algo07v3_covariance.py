"""Compare covariance workspace reuse on complete difficult training fits."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from algo07v3_precovariance_hierarchical_oracle import hierarchical_bound
from benchmark_algo07v3_training_kernel import trial
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_covariance import candidate
from probe_algo07v3_posterior_buffers import training_inputs

from leo.operations.localization_v3_job import runtime_versions, source_bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--expected-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    if request['runtime'] != runtime_versions():
        raise ValueError('Frozen runtime changed')
    expected_paths = {arm: args.expected_root / f'{arm}-0-candidate.json'
                      for arm in ('c0', 'fitted_c')}
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__), *expected_paths.values()]
    paths.extend(Path('tools') / name for name in (
        'algo07v3_precovariance_hierarchical_oracle.py',
        'probe_algo07v3_covariance.py', 'benchmark_algo07v3_training_kernel.py',
        'check_algo07v3_scan_likelihood.py', 'probe_algo07v3_posterior_buffers.py',
        'probe_algo07v3_annotation_arms.py'))
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    bindings.update({r['path']: r['sha256'] for r in source_bindings().values()})
    function, original, changed = candidate('workspace')
    (args.output / 'baseline.py').write_text(original)
    (args.output / 'candidate.py').write_text(changed)
    plan = dict(bindings=bindings, repeats=2, arms=list(expected_paths),
                affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                phase_rounds=5, optimizer_iterations=48, target=1, fold=1)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    rows = []
    for arm, path in expected_paths.items():
        expected = json.loads(path.read_bytes())['signature']
        for pair in range(2):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                d, keep, receipt, seed, split = training_inputs(request)
                before = fingerprint((d['node'], keep))
                operation = hierarchical_bound if side == 'baseline' else function
                measured = trial(d, keep, arm, operation)
                row = dict(arm=arm, pair=pair, side=side, **measured,
                           exact=measured['signature'] == expected, scientific_receipt=receipt,
                           seed=seed, split=split, training_points=int(np.sum(keep)))
                rows.append(row)
                (args.output / f'{arm}-{pair}-{side}.json').write_text(
                    json.dumps(row, indent=2) + '\n')
                print(json.dumps({k: row[k] for k in ('arm', 'pair', 'side', 'seconds',
                                                     'cpu_seconds', 'exact')}), flush=True)
                if not row['exact'] or before != fingerprint((d['node'], keep)):
                    raise ValueError('Complete training changed; retain failed receipt')
    if not all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items()):
        raise ValueError('Sources changed during experiment')
    (args.output / 'result.json').write_text(json.dumps(dict(
        plan=plan, rows=rows, exact=True, full_pipeline_speedup=None,
        runtime_modified=False, production_modified=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
