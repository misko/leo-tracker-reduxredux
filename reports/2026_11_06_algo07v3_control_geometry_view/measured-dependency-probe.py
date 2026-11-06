"""Observe complete control dependencies and exact-key costs without runtime edits."""

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from probe_algo07v3_annotation_arms import load_context
from probe_algo07v3_inclusion_controls import controller
from probe_algo07v3_native_recovery_queue import recovery_trial, signature

from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.operations.localization_v3_job import runtime_versions, validate_request
from leo.storage.localization_v3 import LocalizationV3Store


def array_buffer(value):
    return value if value.flags.c_contiguous else value.tobytes(order='C')


def load_keys(path):
    spec = importlib.util.spec_from_file_location('_archived_control_keys', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = inspect.getsource(module._fingerprint)
    needle = "value.tobytes(order='C')"
    if source.count(needle) != 1:
        raise ValueError('Review changed archived fingerprint')
    scope = dict(vars(module), _array_buffer=array_buffer)
    exec(compile(source.replace(needle, '_array_buffer(value)'),
                 '<external-buffer-key>', 'exec'), scope)
    return module._fingerprint, scope['_fingerprint']


def observed_compute(compute, path):
    """One append-only attribute trace shared by forked arm workers."""
    seen = set()
    original = ScanLikelihood.__getattribute__
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_APPEND, 0o600)

    def access(self, name):
        value = original(self, name)
        key = (os.getpid(), name)
        if key not in seen:
            seen.add(key)
            os.write(fd, (json.dumps(dict(pid=key[0], attribute=name)) + '\n').encode())
        return value

    try:
        with patch.object(ScanLikelihood, '__getattribute__', access):
            return compute()
    finally:
        os.close(fd)


class Dependencies:
    def __init__(self, root, fingerprints):
        self.root, self.fingerprints, self.rows = root, fingerprints, []

    def __call__(self, compute, control, kind, d, inventory, count, option):
        if not control:
            return compute()
        fields = dict(vars(d['scan']))
        for name in ('tracks', 'white', 'rx_basis'):
            fields[name] = fields[name][:count]
        fields.update({f'context.{k}': d[k] for k in
                       ('node', 'keep', 'powers', 'means', 'model', 'entries')})
        fields['inventory.policy'] = inventory['policy']
        timings = []
        for name, value in fields.items():
            values, clocks = [], []
            for fingerprint in self.fingerprints:
                began = time.perf_counter()
                values.append(fingerprint(value))
                clocks.append(time.perf_counter() - began)
            if values[0] != values[1]:
                raise ValueError(f'Buffer fingerprint changed: {name}')
            timings.append(dict(field=name, copy_seconds=clocks[0],
                                buffer_seconds=clocks[1]))
        trace = self.root / f'control-{len(self.rows)}-attributes.jsonl'
        began = time.perf_counter()
        result = observed_compute(compute, trace)
        attributes = sorted({json.loads(line)['attribute']
                             for line in trace.read_text().splitlines()})
        self.rows.append(dict(kind=kind, option=option, fields=timings,
                              observed_seconds=time.perf_counter() - began,
                              attributes=attributes, output_signature=signature(result)))
        return result

    pair = __call__


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path, required=True)
    p.add_argument('--helper', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        p.error('Use three CPU slots and one BLAS thread')
    request = validate_request(json.loads(args.request.read_bytes()))
    if request['runtime'] != runtime_versions():
        raise ValueError('Frozen runtime changed')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, args.helper, Path(__file__)]
    paths += [Path('tools') / name for name in (
        'probe_algo07v3_inclusion_controls.py', 'probe_algo07v3_annotation_arms.py',
        'probe_algo07v3_native_recovery_queue.py', 'check_algo07v3_scan_likelihood.py',
        'profile_algo07v3_training_queue.py')]
    bindings = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    d, inventory, receipt = load_context(request)
    observer = Dependencies(args.output, load_keys(args.helper))
    row = recovery_trial(dict(recovery_context=d, inventory=inventory), controller(observer))
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    if saved['sha256'] != receipt or row['result_signature'] != signature(
            saved['evidence']['audit']['predictive_recovery']):
        raise ValueError('Observed recovery differs from saved native audit')
    if any(hashlib.sha256(Path(q).read_bytes()).hexdigest() != sha
           for q, sha in bindings.items()):
        raise ValueError('Bound source/input changed')
    result = dict(bindings=bindings, controls=observer.rows, recovery=row,
                  saved_native_audit_exact=True, profiling_only=True,
                  dependency_trace_is_not_a_proof_of_completeness=True)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(exact=True, controls=len(observer.rows), seconds=row['seconds'])))


if __name__ == '__main__':
    main()
