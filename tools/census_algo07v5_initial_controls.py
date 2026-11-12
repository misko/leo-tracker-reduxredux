"""Census complete saved initial controls without running numerical inference."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from leo.contracts.digests import canonical_digest
from leo.storage.localization_v3 import LocalizationV3Store
from leo.storage.localization_v4 import LocalizationV4Store

ARMS = ('c0', 'fitted_c')
FIT_ITERATIONS = 48


def exact_bytes(value):
    """Length-framed encoding preserves types and floating-point payload bits."""
    kind = type(value)
    tag = (kind.__module__ + '.' + kind.__qualname__).encode()
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise TypeError('Object arrays have no stable byte identity')
        parts = [repr(value.dtype.descr).encode(), repr(value.shape).encode(),
                 value.tobytes(order='C')]
    elif isinstance(value, np.generic):
        parts = [repr(value.dtype.descr).encode(), value.tobytes()]
    elif kind is dict:
        parts = [exact_bytes((k, v)) for k, v in
                 sorted(value.items(), key=lambda item: exact_bytes(item[0]))]
    elif kind in (list, tuple):
        parts = [exact_bytes(v) for v in value]
    elif kind is float:
        parts = [struct.pack('>d', value)]
    elif kind is complex:
        parts = [struct.pack('>dd', value.real, value.imag)]
    elif kind in (str, int, bool, type(None)):
        parts = [repr(value).encode()]
    elif kind is bytes:
        parts = [value]
    else:
        raise TypeError(f'Unsupported exact value type {kind!r}')
    return b''.join(struct.pack('>Q', len(p)) + p for p in [tag, *parts])


def fingerprint(value):
    return 'sha256:' + hashlib.sha256(exact_bytes(value)).hexdigest()


def differences(a, b, path='$'):
    """Return every differing recursive field, including array metadata/bytes."""
    if type(a) is not type(b):
        return [dict(path=path, reason='type', left=str(type(a)), right=str(type(b)))]
    if isinstance(a, np.ndarray):
        issues = []
        for field, x, y in [('shape', a.shape, b.shape),
                            ('dtype', a.dtype.descr, b.dtype.descr)]:
            if x != y:
                issues.append(dict(path=path + '.' + field, reason='value',
                                   left=repr(x), right=repr(y)))
        if a.tobytes(order='C') != b.tobytes(order='C'):
            issues.append(dict(path=path, reason='array_bytes',
                               left=fingerprint(a), right=fingerprint(b)))
        return issues
    if type(a) is dict:
        aa, bb = ({exact_bytes(k): (k, v) for k, v in obj.items()} for obj in (a, b))
        issues = []
        for key in sorted(aa.keys() | bb.keys()):
            label = repr((aa if key in aa else bb)[key][0])
            if key not in aa or key not in bb:
                issues.append(dict(path=f'{path}[{label}]', reason='missing_field',
                                   missing_in='left' if key not in aa else 'right'))
            else:
                issues.extend(differences(aa[key][1], bb[key][1], f'{path}[{label}]'))
        return issues
    if type(a) in (list, tuple):
        issues = ([] if len(a) == len(b) else
                  [dict(path=path, reason='length', left=len(a), right=len(b))])
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            issues.extend(differences(x, y, f'{path}[{i}]'))
        issues.extend(dict(path=f'{path}[{i}]', reason='missing_item',
                           missing_in='left' if len(a) < len(b) else 'right')
                      for i in range(min(len(a), len(b)), max(len(a), len(b))))
        return issues
    return ([] if exact_bytes(a) == exact_bytes(b) else
            [dict(path=path, reason='scalar_bits', left=fingerprint(a), right=fingerprint(b))])


def compare_initial(initial):
    selected = initial.get('selected_hypothesis')
    winners = [c for c in initial.get('choices', []) if c.get('hypothesis') == selected]
    rows = []
    for arm in ARMS:
        row = dict(arm=arm, selected_hypothesis=selected, fit_iterations=FIT_ITERATIONS,
                   iterations_basis='source policy default; not persisted per fit')
        try:
            if len(winners) != 1:
                raise KeyError('exactly one selected hypothesis required')
            first = winners[0]['arms'][arm]['phase_rounds'][0]
            left, right = first['fit'], initial['zero_phase_control'][arm]
            issues = differences(left, right)
            context = dict(epoch_zero=type(first['epoch']) is int and first['epoch'] == 0,
                           zero_reference=bool(np.asarray(first['phase_reference']).size
                                               and np.all(np.asarray(
                                                   first['phase_reference']) == 0)),
                           zero_start=all(np.array_equal(f['history'][0]['parameters'],
                                                        np.zeros(2)) for f in (left, right)))
            issues.extend(dict(path='context.' + k, reason='required_true')
                          for k, v in context.items() if not v)
            row.update(status='mismatching' if issues else 'matching', context=context,
                       first_fit_sha256=fingerprint(left), control_fit_sha256=fingerprint(right),
                       mismatches=issues)
        except (KeyError, IndexError, TypeError) as exc:
            row.update(status='missing', error=str(exc))
        rows.append(row)
    return rows


def census_request(path):
    raw = path.read_bytes()
    request = json.loads(raw)
    wrapped = 'job' in request
    if wrapped and request.get('algorithm') != 'algo07v4-native-v1':
        raise ValueError('Unsupported wrapped request algorithm')
    job = request['job'] if wrapped else request
    root = Path(job['output_root']).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    store = LocalizationV4Store if wrapped else LocalizationV3Store
    saved = store(root).load(job['identity']['run_id'])
    evidence, receipt = saved['evidence'], saved['receipt']
    provenance = evidence['provenance']
    if (provenance['request_sha256'] != canonical_digest(request)
            or provenance['configuration']['request'] != job
            or evidence['identity'] != job['identity']):
        raise ValueError('Saved evidence/request binding mismatch')
    return dict(request_path=str(path),
                request_file_sha256='sha256:' + hashlib.sha256(raw).hexdigest(),
                request_sha256=canonical_digest(request), output_root=str(root),
                identity=job['identity'], receipt=receipt, receipt_sha256=saved['sha256'],
                archive_sha256=receipt['result_sha256'], archive_bytes=receipt['result_bytes'],
                arms=compare_initial(evidence['audit']['initial']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, action='append', default=[])
    parser.add_argument('--pilot-ledger', type=Path)
    parser.add_argument('--output', type=Path, required=True,
                        help='Explicit local output directory')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.is_relative_to('/mnt/qnap01'):
        parser.error('Output must be local')
    paths = list(args.request)
    binds = {str(Path(__file__).resolve()):
             'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if args.pilot_ledger:
        raw = args.pilot_ledger.read_bytes()
        ledger = json.loads(raw)
        binds[str(args.pilot_ledger.resolve())] = 'sha256:' + hashlib.sha256(raw).hexdigest()
        baseline = [r for r in ledger['runs'] if r['config'] == 'baseline']
        if len(baseline) != 8 or len({r['case'] for r in baseline}) != 8:
            parser.error('Pilot ledger must contain eight distinct baseline cases')
        paths.extend(Path(r['output']) / 'request.json' for r in baseline)
    if not paths:
        parser.error('At least one request or pilot ledger required')
    results = []
    for path in dict.fromkeys(p.resolve() for p in paths):
        try:
            binds[str(path)] = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
            results.append(census_request(path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            results.append(dict(request_path=str(path), error=str(exc),
                                arms=[dict(arm=a, status='missing') for a in ARMS]))
    counts = {s: sum(r['status'] == s for run in results for r in run['arms'])
              for s in ('matching', 'mismatching', 'missing')}
    report = dict(schema_version=1, kind='algo07v5-saved-initial-control-census',
                  input_bindings=binds, requests=results, counts=counts,
                  inference_rerun=False, accuracy_qualification=False, speed_qualification=False)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'census.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(output=str(output / 'census.json'), counts=counts)))
    return int(bool(counts['mismatching'] or counts['missing']))


if __name__ == '__main__':
    raise SystemExit(main())
