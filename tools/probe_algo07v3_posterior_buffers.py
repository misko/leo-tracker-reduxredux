"""External posterior-buffer experiments; arithmetic equivalence is measured, not assumed."""

import argparse
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import algo07v3_prescratch_hierarchical_oracle as reference
from benchmark_algo07v3_training_kernel import kernel
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_annotation_arms import fold_inputs, load_context

from leo.analysis.localization_v3 import prediction
from leo.analysis.localization_v3.recovery_partitions import planned_split
from leo.operations.localization_v3_job import runtime_versions


def candidate_function(variant):
    source = inspect.getsource(reference.hierarchical_bound)
    code = source

    def replace(before, after):
        nonlocal code
        if code.count(before) != 1:
            raise ValueError('Review changed posterior source before probing')
        code = code.replace(before, after)

    if variant in ('metadata', 'buffers', 'combined'):
        replace('    identity = np.eye(width)',
                "    identity = np.eye(width, order='F')\n"
                '    upper_pivots = np.arange(width, dtype=np.int32)')
        replace('_solve_factor(root.T, np.arange(width, dtype=np.int32),',
                '_solve_factor(root.T, upper_pivots,')
    if variant in ('buffers', 'combined'):
        replace('    def posterior(weight, precision, covariance):',
                '    variance_work = [np.empty(indices.shape)\n'
                '                     for _, indices, _ in variance_blocks]\n\n'
                '    def posterior(weight, precision, covariance):')
        replace('''        for group_indices, indices, variance_matrices in variance_blocks:
            products = covariance.ravel()[indices] * variance_matrices''',
                '''        for (group_indices, indices, variance_matrices), products in zip(
                variance_blocks, variance_work, strict=True):
            np.take(covariance.ravel(), indices, out=products, mode='clip')
            np.multiply(products, variance_matrices, out=products)''')
    if variant == 'combined':
        replace('''        mean = (
            _solve_factor(root.T, upper_pivots,
                          _solve_factor(lu, pivots, rhs))
            if width else rhs.copy()
        )
        cov = None
        if covariance:
            inv_root = _solve_factor(lu, pivots, identity) if width else identity.copy()''',
                '''        if covariance and width:
            solved = _solve_factor(lu, pivots, np.column_stack((rhs, identity)))
            lower_mean, inv_root = solved[:, 0], solved[:, 1:]
        else:
            lower_mean = _solve_factor(lu, pivots, rhs) if width else rhs.copy()
            inv_root = identity.copy() if covariance else None
        mean = _solve_factor(root.T, upper_pivots, lower_mean) if width else rhs.copy()
        cov = None
        if covariance:''')
    if variant not in ('metadata', 'buffers', 'combined'):
        raise ValueError('Unknown posterior experiment')
    scope = dict(vars(reference))
    exec(compile(code, f'<posterior-{variant}>', 'exec'), scope)
    return scope['hierarchical_bound'], source, code


def training_inputs(request):
    d, inv, receipt = load_context(request)
    d, i, full, n, seed, plan = fold_inputs(d, inv, 1, 1)
    train, _, split = planned_split(full, d['scan'].tracks[i]['times'], seed, plan)
    return d, d['keep'] & train[:n], receipt, int(seed), split


def capture(d, keep, arm):
    class Captured(Exception):
        pass

    values = []
    def receive(*args, **kwargs):
        values.extend((args, kwargs))
        raise Captured

    try:
        with kernel(receive):
            prediction.fit_training(d, d['node'], keep, arm)
    except Captured:
        return values
    raise ValueError('Training never called the hierarchical likelihood')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path(reference.__file__), Path('tools/benchmark_algo07v3_training_kernel.py'),
             Path('tools/probe_algo07v3_annotation_arms.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the frozen numerical runtime')
    variants = {v: candidate_function(v) for v in ('metadata', 'buffers', 'combined')}
    for variant, (_, _, changed) in variants.items():
        (args.output / f'{variant}.py').write_text(changed)
    (args.output / 'original.py').write_text(variants['metadata'][1])
    (args.output / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
        target=1, fold=1, kernel_only=True, production_modified=False), indent=2) + '\n')
    rows = []
    for arm in ('c0', 'fitted_c'):
        d, keep, receipt, seed, split = training_inputs(request)
        positional, keywords = capture(d, keep, arm)
        inputs_before = fingerprint((positional, keywords))
        expected = reference.hierarchical_bound(*positional, **keywords)
        signature = fingerprint(expected)
        for variant, (candidate, _, _) in variants.items():
            actual = candidate(*positional, **keywords)
            exact = fingerprint(actual) == signature
            differing = [k for k in expected if fingerprint(actual[k]) != fingerprint(expected[k])]
            row = dict(arm=arm, variant=variant, exact=exact, differing_fields=differing,
                       shape=positional[1].shape,
                       precision_iterations=expected['precision_iterations'],
                       scientific_receipt=receipt, seed=seed, split=split, timings=[])
            if exact:
                for pair in range(3):
                    order = (('baseline', 'candidate') if pair % 2 == 0
                             else ('candidate', 'baseline'))
                    for side in order:
                        operation = (reference.hierarchical_bound
                                     if side == 'baseline' else candidate)
                        begin, cpu = time.perf_counter(), time.process_time()
                        result = operation(*positional, **keywords)
                        elapsed, used = time.perf_counter() - begin, time.process_time() - cpu
                        assert fingerprint(result) == signature
                        row['timings'].append(dict(pair=pair, side=side, seconds=elapsed,
                                                   cpu_seconds=used))
            assert inputs_before == fingerprint((positional, keywords))
            rows.append(row)
            (args.output / f'{arm}-{variant}.json').write_text(json.dumps(row, indent=2) + '\n')
            print(json.dumps({k: row[k] for k in ('arm', 'variant', 'exact', 'shape',
                                                 'differing_fields', 'timings')}), flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    (args.output / 'result.json').write_text(json.dumps(dict(
        rows=rows, bindings=bindings, complete=True, kernel_only=True,
        full_pipeline_speedup=None, production_modified=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
