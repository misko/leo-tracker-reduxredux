"""External exact control reuse using a scan view without discovery geometry."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from probe_algo07v3_annotation_arms import load_context
from probe_algo07v3_inclusion_controls import ControlPairs, controller
from probe_algo07v3_native_recovery_queue import recovery_trial, signature

from leo.analysis.localization_v3.recovery_controller import recover_tracks
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.operations.localization_v3_job import runtime_versions, validate_request
from leo.operations.localization_v3_parallel import _ordered
from leo.storage.localization_v3 import LocalizationV3Store


class ControlViewPairs(ControlPairs):
    def __call__(self, compute, control, kind, d, inventory, count, option):
        if (not control or d.get('numerical_policy') is not None
                or 'problem_factory' in d or type(d['scan']) is not ScanLikelihood
                or (kind == 'fit_shared' and option)
                or any(callable(v) for v in vars(d['scan']).values())):
            return compute()
        view = copy.copy(d['scan'])
        # Control construction uses per-family geometry. The original discovery
        # cache is unavailable to this computation, not merely omitted from its key.
        vars(view).pop('geometry', None)
        with patch.dict(d, scan=view):
            return super().__call__(compute, control, kind, d, inventory, count, option)

    pair = __call__


def trial(prepared, side):
    pairs = ControlViewPairs(True)
    row = recovery_trial(prepared, controller(pairs) if side == 'candidate' else recover_tracks)
    row['controls'] = pairs.rows
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reverse', action='store_true')
    args = p.parse_args()
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        p.error('Use three CPUs and one BLAS thread')
    request = validate_request(json.loads(args.request.read_bytes()))
    if request['runtime'] != runtime_versions():
        raise ValueError('Frozen runtime changed')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__)]
    paths += [Path('tools') / name for name in (
        'probe_algo07v3_inclusion_controls.py', 'probe_algo07v3_annotation_arms.py',
        'probe_algo07v3_native_recovery_queue.py', 'check_algo07v3_scan_likelihood.py',
        'profile_algo07v3_training_queue.py')]
    bindings = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    d, inventory, receipt = load_context(request)
    prepared = dict(recovery_context=d, inventory=inventory)
    sequence = ['candidate', 'baseline'] if args.reverse else ['baseline', 'candidate']
    rows, expected = [], None
    for side in sequence:
        row = _ordered(lambda _, side=side: trial(prepared, side), [0], workers=1)[0]
        actual = {k: row[k] for k in ('result_signature', 'selection_signature',
                                      'stage_signatures', 'input_signature')}
        if expected is None:
            expected = actual
        row.update(side=side, exact=actual == expected)
        rows.append(row)
        (args.output / f'{side}.json').write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps({k: row[k] for k in ('side', 'seconds', 'cpu_seconds', 'exact')}),
              flush=True)
        if not row['exact']:
            raise ValueError('Complete recovery, inputs or selection changed')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    reference = signature(saved['evidence']['audit']['predictive_recovery'])
    if saved['sha256'] != receipt or any(r['result_signature'] != reference for r in rows):
        raise ValueError('Saved native recovery audit changed')
    if any(hashlib.sha256(Path(q).read_bytes()).hexdigest() != sha
           for q, sha in bindings.items()):
        raise ValueError('Bound source/input changed')
    result = dict(bindings=bindings, rows=rows, sequence=sequence,
                  saved_native_audit_exact=True, exact=True, runtime_modified=False,
                  baseline_has_no_fingerprint_overhead=True)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
