"""Replay complete joint fits from one native checkpoint; no runtime patch persists."""

import argparse
import hashlib
import inspect
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from probe_algo07v3_final_joint_reuse import candidate
from probe_algo07v3_joint_audit import ProbeComplete, cpu, qualified_inputs, signature

from leo.analysis.localization_v3 import joint_recovery as joint
from leo.operations.localization_v3_job import execute, validate_request
from leo.operations.localization_v3_parallel import _ordered


def measure(operation, args, save):
    """Fork each trial before original or candidate can warm its parent context."""
    rows, expected = [], None
    for index, side in enumerate(('baseline', 'candidate', 'candidate', 'baseline')):
        def trial(_, side=side):
            context = args[0]
            policy = context.get('numerical_policy')
            before = signature(policy.receipt) if policy else None
            calls = []
            density = joint.joint_density

            def timed(*values):
                inputs = signature(values[1:])
                policy = values[0].get('numerical_policy')
                mode = True if policy is None else policy.joint_contraction_optimized
                start, used = time.perf_counter(), cpu()
                result = density(*values)
                calls.append(dict(seconds=time.perf_counter() - start,
                                  cpu_seconds=cpu() - used,
                                  inputs=inputs, optimize_contractions=mode,
                                  pairs=result['phase_pair_count'],
                                  result=signature(result)))
                return result

            with patch.object(joint, 'joint_density', timed):
                fn = operation if side == 'baseline' else candidate(
                    operation.__name__, inspect.getsource(operation))[0]
                start, used = time.perf_counter(), cpu()
                result = fn(*args)
                elapsed, used = time.perf_counter() - start, cpu() - used
            after = signature(policy.receipt) if policy else None
            return dict(seconds=elapsed, cpu_seconds=used, result=signature(result),
                        policy_before=before, policy_after=after, calls=calls)

        row = _ordered(trial, [0], workers=1)[0]
        science = (row['result'], row['policy_before'], row['policy_after'])
        if expected is None:
            expected = science
        row.update(index=index, side=side, exact=science == expected)
        save(row)
        rows.append(row)
        if not row['exact']:
            raise ValueError('Complete fit or ordered numerical receipts changed')
    baseline = [r for r in rows if r['side'] == 'baseline']
    for row in rows:
        expected_calls = baseline[0]['calls']
        if row['side'] == 'candidate':
            expected_calls = expected_calls[:-1]
        keys = ('inputs', 'optimize_contractions', 'pairs', 'result')
        if [tuple(v[k] for k in keys) for v in row['calls']] != [
                tuple(v[k] for k in keys) for v in expected_calls]:
            raise ValueError('Expected exactly one final duplicate integration removal')
    return rows


def main(*, measurement=measure, scope='first native c0 joint fit only',
         extra_dependencies=(), export_candidates=True):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-comparison', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=('predictive', 'numerical'), required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01') or sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Local output and CPU slots 0,1,2 required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('One BLAS thread required')
    request = validate_request(json.loads(args.request.read_bytes()))
    qualified = qualified_inputs(args.native_comparison, request)
    paths = [*Path('src').rglob('*.py'), *Path('src/leo/analysis').glob('*.so'),
             Path(__file__), Path('tools/probe_algo07v3_final_joint_reuse.py'),
             Path('tools/probe_algo07v3_joint_audit.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             args.request, args.native_comparison, *qualified, *extra_dependencies]
    bundle = Path(request['native_input']['path']).parent
    manifest = bundle / 'input-bindings.json'
    paths.append(manifest)
    for name, sha in json.loads(manifest.read_bytes())['files'].items():
        path = (bundle / name).resolve()
        if (not path.is_relative_to(bundle.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != sha):
            raise ValueError('Frozen native input changed')
        paths.append(path)
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    root.mkdir(exist_ok=False)
    (root / 'plan.json').write_text(json.dumps(dict(bindings=bindings, stage=args.stage,
        cpus=[0, 1, 2], blas_threads=1, sequence=['baseline', 'candidate', 'candidate', 'baseline'],
        scope=scope, production_modified=False,
        full_pipeline_speedup=None), indent=2) + '\n')
    if export_candidates:
        for name in ('_fit_lbfgsb', '_fit_powell'):
            (root / f'{name}-candidate.py').write_text(candidate(name)[1] + '\n')
    operation = joint._fit_lbfgsb

    def save(row):
        (root / f"{row['index']}-{row['side']}.json").write_text(json.dumps(row, indent=2))
        print(json.dumps({k: row[k] for k in ('index', 'side', 'seconds', 'cpu_seconds', 'exact')}),
              flush=True)

    def observed(context, targets, arm, method, phase_step):
        stage = 'numerical' if context.get('numerical_policy') is not None else 'predictive'
        if stage != args.stage or arm != 'c0' or method != 'joint':
            return operation(context, targets, arm, method, phase_step)
        rows = measurement(operation, (context, targets, arm, method, phase_step), save)
        (root / 'result.json').write_text(json.dumps(dict(rows=rows, exact=True), indent=2))
        raise ProbeComplete()

    native = dict(request, output_root=str(root / 'unused-publication'), evaluation_reference=None)
    with (root / 'prefix.jsonl').open('x') as log:
        def emit(row):
            log.write(json.dumps(row) + '\n')
            log.flush()
        with patch.object(joint, '_fit_lbfgsb', observed):
            try:
                execute(native, emit=emit)
            except ProbeComplete:
                pass
            else:
                raise ValueError('Requested native joint fit was not reached')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound sources or inputs changed')
    (root / 'verified.json').write_text(json.dumps(dict(bindings_unchanged=True,
        exact_complete_fit=True, full_pipeline_speedup=None)))


if __name__ == '__main__':
    main()
