"""External exact audit against the archived production family-policy JSON.

This reads historical results only for comparison, never for candidate inference.
JSON has no ndarray dtype; the fresh oracle fingerprint supplies the declared
representation. Every restored value and shape must survive conversion exactly.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

OPERATIONAL_FIELDS = frozenset((
    'case', 'algorithm', 'baseline_sha256', 'engine_sha256', 'history_sha256',
    'history_forecast_sha256', 'seconds',
))


def compare_persisted(value, expected, path='root'):
    if isinstance(expected, dict) and expected.get('type') == 'array':
        original = np.asarray(value)
        dtype = np.dtype(expected['dtype'])
        if dtype.kind == 'b' and original.dtype.kind != 'b':
            raise ValueError(f'Boolean representation changed: {path}')
        restored = np.asarray(value, dtype=dtype)
        if restored.tolist() != value or fingerprint(restored) != expected:
            raise ValueError(f'Array value/shape differs: {path}')
    elif isinstance(expected, dict) and expected.get('type') == 'float':
        if type(value) is not float or value.hex() != expected['hex']:
            raise ValueError(f'Floating value differs: {path}')
    elif isinstance(expected, dict):
        if not isinstance(value, dict) or set(value) != set(expected):
            raise ValueError(f'Fields differ: {path}')
        for key, item in expected.items():
            compare_persisted(value[key], item, path+'/'+key)
    elif isinstance(expected, list):
        if not isinstance(value, list) or len(value) != len(expected):
            raise ValueError(f'List shape differs: {path}')
        for i, (a, b) in enumerate(zip(value, expected, strict=True)):
            compare_persisted(a, b, path+'/'+str(i))
    elif type(value) is not type(expected) or value != expected:
        raise ValueError(f'Value differs: {path}')


def compare(archived, candidate):
    original = {k:v for k,v in archived.items() if k not in OPERATIONAL_FIELDS}
    compare_persisted(original, candidate['history_policy'])
    return dict(exact=True, excluded_operational_fields=sorted(OPERATIONAL_FIELDS),
                scope='Persisted family-policy scientific fields; not final ALGO07 publication')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archived', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    archive_bytes, candidate_bytes = args.archived.read_bytes(), args.candidate.read_bytes()
    result = compare(json.loads(archive_bytes), json.loads(candidate_bytes))
    result.update(archived_path=str(args.archived), candidate_path=str(args.candidate),
                  archived_sha256=hashlib.sha256(archive_bytes).hexdigest(),
                  candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest())
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(result, sort_keys=True))
