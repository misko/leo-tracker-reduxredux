"""Conservative full-worker diff; operational differences are NOT silently ignored.

Only the declared private-store path prefix is normalized. This diagnostic can
locate the first differing scientific or operational field before a versioned
schema-specific comparator qualifies any differences. It is not a parity waiver.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from leo.cli.algo07_profile import write_new


def load_export(root):
    descriptor = json.loads((root/'descriptor.json').read_text())
    if descriptor['kind'] != 'fast-graph-worker-evidence':
        raise ValueError('Verified worker evidence export required')
    files = {}
    for name, expected in descriptor['files'].items():
        path = root/name
        if (not path.resolve(strict=True).is_relative_to(root.resolve()) or path.is_symlink()
                or 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError('Export changed: '+name)
        files[name] = path
    actual = {str(p.relative_to(root)) for p in (root/'worker').rglob('*') if p.is_file()}
    if set(files) != actual:
        raise ValueError('Export inventory changed')
    return descriptor, files


def normalized(value, root):
    if isinstance(value, str):
        if value == root or value.startswith(root+'/'):
            return '<PRIVATE_STORE>'+value[len(root):]
        return value
    if isinstance(value, list):
        return [normalized(v, root) for v in value]
    if isinstance(value, dict):
        result = {normalized(k, root): normalized(v, root) for k, v in value.items()}
        if len(result) != len(value):
            raise ValueError('Path normalization introduced duplicate keys')
        return result
    return value


def differences(left, right, path=''):
    if type(left) is not type(right):
        yield dict(path=path, kind='type', reference_type=type(left).__name__,
                   candidate_type=type(right).__name__)
    elif isinstance(left, dict):
        if left.keys() != right.keys():
            yield dict(path=path, kind='keys', reference_only=sorted(left.keys()-right.keys()),
                       candidate_only=sorted(right.keys()-left.keys()))
        for key in sorted(left.keys() & right.keys()):
            escaped = key.replace('~', '~0').replace('/', '~1')
            yield from differences(left[key], right[key], path+'/'+escaped)
    elif isinstance(left, list):
        if len(left) != len(right):
            yield dict(path=path, kind='length', reference=len(left), candidate=len(right))
        for index, (a, b) in enumerate(zip(left, right, strict=False)):
            yield from differences(a, b, path+'/'+str(index))
    elif isinstance(left, float):
        if not math.isfinite(left) or not math.isfinite(right) or left.hex() != right.hex():
            yield dict(path=path, kind='float', reference=repr(left), candidate=repr(right))
    elif left != right:
        yield dict(path=path, kind='value', reference=left, candidate=right)


def compare(left, right):
    a, b = load_export(left), load_export(right)
    for key in ('input_sha256', 'model_version', 'job_id'):
        if a[0][key] != b[0][key]:
            raise ValueError('Different worker input or model')
    rows = []
    af, bf = a[1], b[1]
    for name in sorted(af.keys() | bf.keys()):
        if name not in af or name not in bf:
            rows.append(dict(file=name, kind='missing_file', reference=name in af,
                             candidate=name in bf))
            continue
        if a[0]['files'][name] == b[0]['files'][name]:
            continue
        if name.endswith('.json'):
            x, y = [normalized(json.loads(files[name].read_text()), desc['source_store_root'])
                    for desc, files in (a, b)]
            rows.extend(dict(file=name, **row) for row in differences(x, y))
        else:
            rows.append(dict(file=name, kind='bytes'))
    return dict(strict_equal=not rows, differences=rows,
                counts=dict(Counter(row['kind'] for row in rows)),
                reference_files=len(af), candidate_files=len(bf),
                operational_differences_waived=False, scientific_parity_qualified=False,
                normalization='Declared private-store path prefix only; zero numeric tolerance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.reference, args.candidate)
    write_new(args.output, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'differences'}))
