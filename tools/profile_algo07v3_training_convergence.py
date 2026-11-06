"""Observe fold/phase precision iterations without changing numerical work."""

import argparse
import hashlib
import json
import os
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_annotation_arms import fold_inputs, load_context

from leo.analysis.localization_v3 import event_position, history_position, prediction
from leo.analysis.localization_v3.recovery_partitions import planned_split
from leo.operations.localization_v3_job import runtime_versions


@contextmanager
def observe(rows):
    originals = [(module, module.hierarchical_bound)
                 for module in (event_position, history_position)]
    original_fit = prediction.fit
    phase = [-1]

    def fit(*args, **kwargs):
        phase[0] += 1
        return original_fit(*args, **kwargs)

    def wrap(operation):
        def call(*args, **kwargs):
            began = time.perf_counter()
            result = operation(*args, **kwargs)
            elapsed = time.perf_counter() - began
            rows.append(dict(phase=phase[0], seconds=elapsed, points=len(args[0]),
                             width=args[1].shape[1], iterations=result['precision_iterations'],
                             final_change=result['final_log_precision_change']))
            return result
        return call

    try:
        prediction.fit = fit
        for module, operation in originals:
            module.hierarchical_bound = wrap(operation)
        yield phase
    finally:
        prediction.fit = original_fit
        for module, operation in originals:
            module.hierarchical_bound = operation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--expected-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('One CPU and one BLAS thread required')
    args.output.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    assert request['runtime'] == runtime_versions()
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request,
             Path('tools/probe_algo07v3_annotation_arms.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    paths.extend(args.expected_root / f'{arm}-0-candidate.json' for arm in ('c0', 'fitted_c'))
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    plan = dict(bindings=bindings, target=1, folds=[0, 1, 2], arms=['c0', 'fitted_c'],
                runtime_modified=False, profiler_only=True)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    results = []
    for fold in (0, 1, 2):
        for arm in ('c0', 'fitted_c'):
            # Hard-fold full histories already have a qualified frozen signature.
            # Fast folds execute an unobserved control before the observer.
            expected = (json.loads((args.expected_root / f'{arm}-0-candidate.json').read_bytes())[
                'signature'] if fold == 1 else None)
            sides = ['observed'] if expected is not None else ['control', 'observed']
            for side in sides:
                d, inv, receipt = load_context(request)
                d, i, full, n, seed, split_plan = fold_inputs(d, inv, 1, fold)
                train, _, split = planned_split(
                    full, d['scan'].tracks[i]['times'], seed, split_plan)
                keep = d['keep'] & train[:n]
                before = fingerprint((d['node'], keep))
                rows = []
                with (observe(rows) if side == 'observed' else nullcontext()) as phase:
                    began, used = time.perf_counter(), time.process_time()
                    p, x, meta = prediction.fit_training(
                        d, d['node'], keep, arm, record_optimizer=True)
                    seconds, cpu = time.perf_counter() - began, time.process_time() - used
                    if phase is not None:
                        phase[0] = 'signature'
                    actual = fingerprint(dict(x=x, meta=meta, reference=p.reference,
                                              state=p.state(x), calculate=p.calculate(x)))
                if side == 'control':
                    expected = actual
                row = dict(fold=fold, arm=arm, side=side, seed=int(seed), split=split,
                           scientific_receipt=receipt, seconds=seconds, cpu_seconds=cpu,
                           exact=actual == expected, calls=rows, signature=actual)
                results.append(row)
                (args.output / f'{fold}-{arm}-{side}.json').write_text(
                    json.dumps(row, indent=2) + '\n')
                assert row['exact'] and before == fingerprint((d['node'], keep))
                print(json.dumps({k: row[k] for k in ('fold', 'arm', 'side', 'seconds', 'exact')}),
                      flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    (args.output / 'result.json').write_text(json.dumps(dict(
        plan=plan, results=results, exact=True, full_pipeline_speedup=None), indent=2) + '\n')


if __name__ == '__main__':
    main()
