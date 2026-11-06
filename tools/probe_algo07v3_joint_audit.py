"""Measure real numerical-audit grids from identical forked native checkpoints.

External diagnostic, stopped after the first direct joint quadrature. This is
not a complete pipeline clock and never supplies results to production.
"""

import argparse
import hashlib
import json
import os
import resource
import time
from pathlib import Path
from unittest.mock import patch

from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import joint_recovery as joint
from leo.operations.localization_v3_job import execute, validate_request
from leo.operations.localization_v3_parallel import _ordered, map_grid_batches


class ProbeComplete(BaseException):
    """Stop at the measured checkpoint without inventing a scientific result."""


def signature(value):
    return hashlib.sha256(json.dumps(fingerprint(value), sort_keys=True).encode()).hexdigest()


def cpu():
    return sum(r.ru_utime + r.ru_stime for r in (
        resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)))


def qualified_inputs(comparison_path, request):
    comparison = json.loads(comparison_path.read_bytes())
    if not comparison['exact_owned_science_and_artifacts'] or not comparison['both_c_arms']:
        raise ValueError('Complete native qualification required before profiling')
    paths, requests = [], []
    for name, sha in comparison['input_bindings'].items():
        path = Path(name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('Native comparison dependency changed')
        paths.append(path)
        if path.name in ('baseline-request.json', 'candidate-request.json'):
            requests.append(json.loads(path.read_bytes()))
    expected = {k: v for k, v in request.items() if k != 'output_root'}
    if len(requests) != 2 or any(
            {k: v for k, v in r.items() if k != 'output_root'} != expected for r in requests):
        raise ValueError('Native qualification belongs to different inputs')
    return paths


def measure_trials(operation, args, mapper, save):
    """Every trial forks from the same unchanged live problem and orbit caches."""
    rows, expected = [], None
    for index, side in enumerate(('baseline', 'candidate', 'candidate', 'baseline')):
        def run(_, side=side):
            policy = args[3].get('numerical_policy')
            before = signature(policy.receipt) if policy else None
            began, used = time.perf_counter(), cpu()
            scores = operation(*args, mapper if side == 'candidate' else None)
            seconds, used = time.perf_counter() - began, cpu() - used
            after = signature(policy.receipt) if policy else None
            if before != after:
                raise ValueError('Audit quadrature changed numerical receipts')
            return dict(seconds=seconds, cpu_seconds=used, score_signature=signature(scores),
                        scores=scores.tolist(), policy_signature=after,
                        max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        row = _ordered(run, [0], workers=1)[0]
        science = (row['score_signature'], row['policy_signature'])
        if expected is None:
            expected = science
        row.update(index=index, side=side, exact=science == expected)
        save(row)
        rows.append(row)
        if not row['exact']:
            raise ValueError('Complete audit grid differs from serial reference')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--native-comparison', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01') or sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Local output and exactly CPU slots 0,1,2 required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('One BLAS thread required')
    request = validate_request(json.loads(args.request.read_bytes()))
    qualified = qualified_inputs(args.native_comparison, request)
    root.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), *Path('src/leo/analysis').glob('*.so'),
             Path(__file__), Path('tools/check_algo07v3_scan_likelihood.py'),
             args.request, args.native_comparison, *qualified]
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
    (root / 'plan.json').write_text(json.dumps(dict(bindings=bindings, cpus=[0, 1, 2],
        blas_threads=1, sequence=['baseline', 'candidate', 'candidate', 'baseline'],
        scope='first native direct joint-audit quadrature',
        production_modified=False, pipeline_speedup=None), indent=2) + '\n')
    operation = joint._quadrature_scores

    def save(row):
        (root / f"{row['index']}-{row['side']}.json").write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps({k: row[k] for k in ('index', 'side', 'seconds', 'cpu_seconds', 'exact')}),
              flush=True)

    def observed(families, problem, position, context, method, offsets, mapper=None):
        policy = context.get('numerical_policy')
        if method != 'joint' or policy is None or policy.joint_contraction_optimized:
            return operation(families, problem, position, context, method, offsets, mapper)
        values = (families, problem, position, context, method, offsets)
        rows = measure_trials(operation, values, map_grid_batches, save)
        (root / 'result.json').write_text(json.dumps(dict(rows=rows,
            offsets_km=offsets.tolist(), position_km=position.tolist(), exact=True), indent=2))
        raise ProbeComplete()

    native = dict(request, output_root=str(root / 'unused-publication'), evaluation_reference=None)
    with (root / 'prefix.jsonl').open('x') as log:
        def emit(row):
            log.write(json.dumps(row) + '\n')
            log.flush()
        with patch.object(joint, '_quadrature_scores', observed):
            try:
                execute(native, emit=emit)
            except ProbeComplete:
                pass
            else:
                raise ValueError('Native direct quadrature was not reached')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound dependencies changed')
    (root / 'verified.json').write_text(json.dumps(dict(bindings_unchanged=True,
        exact_complete_grid=True, scope='audit quadrature only', full_pipeline_speedup=None)))


if __name__ == '__main__':
    main()
